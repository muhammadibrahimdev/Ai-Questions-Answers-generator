import tempfile
import uuid
from pathlib import Path

from fastapi import FastAPI, UploadFile, File, HTTPException, Request
from fastapi.responses import FileResponse

from src.helper import count_pdf_pages, llm_pipeline, NoTextError
from src.rate_limit import is_ip_blocked, block_ip, unblock_ip

BASE_DIR = Path(__file__).resolve().parent

# Vercel's disk is read-only except the temp folder
UPLOAD_DIR = Path(tempfile.gettempdir()) / "uploads"
UPLOAD_DIR.mkdir(exist_ok=True, parents=True)

MAX_PAGES = 10
MAX_BYTES = 4 * 1024 * 1024  # Vercel rejects bodies over ~4.5 MB anyway

app = FastAPI()


@app.get("/")
def home():
    # index.html lives in public/ (preferred) or templates/ (old location)
    for folder in ("public", "templates"):
        index = BASE_DIR / folder / "index.html"
        if index.exists():
            return FileResponse(index)
    raise HTTPException(status_code=404, detail="index.html not found.")


@app.post("/generate")
def generate_questions(request: Request, file: UploadFile = File(...)):
    # 1. Quick rejection for IPs that already used their one try
    if is_ip_blocked(request):
        raise HTTPException(
            status_code=403,
            detail="This IP has already used the generator.",
        )

    # 2. Basic file checks
    if not (file.filename or "").lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF files are allowed.")

    contents = file.file.read(MAX_BYTES + 1)
    if len(contents) > MAX_BYTES:
        raise HTTPException(status_code=413, detail="File too large (max 4 MB).")

    # Random file name so two users never clash
    file_path = UPLOAD_DIR / f"{uuid.uuid4().hex}.pdf"
    file_path.write_bytes(contents)

    try:
        # 3. Page limit (checked on the server, not only in the browser)
        try:
            pages = count_pdf_pages(str(file_path))
        except Exception:
            raise HTTPException(status_code=400, detail="Invalid PDF file.")

        if pages > MAX_PAGES:
            raise HTTPException(
                status_code=400,
                detail=f"PDF has {pages} pages. Maximum allowed is {MAX_PAGES} pages.",
            )

        # 4. Use up the one try BEFORE generating, so parallel requests
        #    cannot sneak through. It is given back if generation fails.
        if not block_ip(request):
            raise HTTPException(
                status_code=403,
                detail="This IP has already used the generator.",
            )

        try:
            results = llm_pipeline(str(file_path))
        except NoTextError as e:
            unblock_ip(request)
            raise HTTPException(status_code=400, detail=str(e))
        except Exception as e:
            unblock_ip(request)
            print(f"Generation failed: {e!r}")  # visible in Vercel logs
            raise HTTPException(
                status_code=500,
                detail="Something went wrong while generating. Please try again.",
            )

        if not results:
            unblock_ip(request)
            raise HTTPException(
                status_code=500,
                detail="No questions could be generated from this PDF.",
            )

        return {"status": "success", "questions_answers": results}

    finally:
        file_path.unlink(missing_ok=True)


@app.get("/health")
def health():
    return {"status": "ok"}