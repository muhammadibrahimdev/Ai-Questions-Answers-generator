prompt_template = """
Generate 10 relevant, non-duplicate questions from the provided text. Cover its key information. Output questions only, numbered sequentially, one per line. No headings or answers.
Generate complete questions only. Never output an unfinished question. only 10 questions
Text:
{text}
"""


refine_template = """
Refine the existing questions using the new text. Add important missing questions, remove duplicates, and keep all questions grounded in the source. Output the complete question list only, numbered sequentially, one per line. No headings or answers.
Generate complete questions only. Never output an unfinished question. only 10 questions
Existing questions:
{existing_answer}

New text:
{text}
"""