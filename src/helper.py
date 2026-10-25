import os
import re

from dotenv import load_dotenv
from pypdf import PdfReader
from langchain_core.documents import Document
from langchain_core.prompts import PromptTemplate
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_groq import ChatGroq
from langchain_classic.chains.summarize import load_summarize_chain

from src.prompt import prompt_template, refine_template

load_dotenv()


class NoTextError(Exception):
    """PDF has no readable text (for example a scanned PDF)."""


def count_pdf_pages(file_path: str) -> int:
    return len(PdfReader(file_path).pages)


def extract_text(file_path: str) -> str:
    reader = PdfReader(file_path)
    pages = [(page.extract_text() or "") for page in reader.pages]
    return "\n".join(pages).strip()


NOT_FOUND = "I could not find this information in the document."
MAX_QUESTIONS = 15


def generate_answers(llm, text: str, questions: list[str]) -> list[str]:
    """One LLM call that answers all questions from the document text."""
    context = text[:20000]  # keeps the request small for Groq's free limits
    numbered = "\n".join(f"{i}. {q}" for i, q in enumerate(questions, 1))

    prompt = f"""Answer each question using only the document below.

Rules:
- Answer each question in 2-4 sentences.
- If the answer is not in the document, answer exactly: {NOT_FOUND}
- Output exactly one line per question, in this format: A<number>: <answer>
- Do not write anything else.

Document:
{context}

Questions:
{numbered}
"""
    reply = str(llm.invoke(prompt).content)

    # Tolerant parser: accepts "A1: ...", "**A1:** ...", "1. ...", "Answer 1: ..."
    # and joins answers that continue on the next line.
    answers = {}
    current = None
    for line in reply.splitlines():
        clean = line.replace("*", "").replace("`", "").strip()
        if not clean:
            continue
        match = re.match(r"(?:A|Answer\s*)?(\d+)\s*[:.)]\s*(.*)", clean, re.IGNORECASE)
        if match and 1 <= int(match.group(1)) <= len(questions):
            current = int(match.group(1))
            answers[current] = match.group(2).strip()
        elif current is not None:
            answers[current] = (answers[current] + " " + clean).strip()

    if not answers:
        # shows up in your terminal / Vercel logs so we can see what the model sent
        print("Could not parse answers. Raw model reply:\n", reply[:2000])

    return [answers.get(i) or NOT_FOUND for i in range(1, len(questions) + 1)]


def llm_pipeline(file_path: str) -> list[dict]:
    """Reads the PDF and returns a list of {"question": ..., "answer": ...}."""
    if not os.getenv("GROQ_API_KEY"):
        raise RuntimeError("GROQ_API_KEY is not set.")

    text = extract_text(file_path)
    if len(text) < 50:
        raise NoTextError(
            "Could not read any text from this PDF. "
            "It may be a scanned/image-only PDF."
        )

    # Plain character splitter: no tiktoken download, works fine on Vercel
    splitter = RecursiveCharacterTextSplitter(chunk_size=20000, chunk_overlap=800)
    docs = [Document(page_content=t) for t in splitter.split_text(text)]

    llm = ChatGroq(model="openai/gpt-oss-20b", temperature=0.3)

    question_prompt = PromptTemplate(
        template=prompt_template,
        input_variables=["text"],
    )
    refine_prompt = PromptTemplate(
        template=refine_template,
        input_variables=["existing_answer", "text"],
    )

    chain = load_summarize_chain(
        llm=llm,
        chain_type="refine",
        question_prompt=question_prompt,
        refine_prompt=refine_prompt,
    )

    result = chain.run(docs)

    questions = []
    for line in result.splitlines():
        line = line.strip()
        if line.endswith("?"):
            # remove leading "1." / "2)" / "- " the model adds, the page numbers them itself
            line = re.sub(r"^(\d+\s*[.)]|[-*•])\s*", "", line).strip()
            questions.append(line)
    questions = questions[:MAX_QUESTIONS]

    if not questions:
        return []

    answers = generate_answers(llm, text, questions)
    return [{"question": q, "answer": a} for q, a in zip(questions, answers)]