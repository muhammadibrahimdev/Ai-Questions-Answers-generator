# AI Question & Answer Generator

Upload a PDF and get AI-generated questions with answers, plus a CSV download.

**Live demo:** _add your Vercel link here_

## Features

- PDF upload (max 10 pages, max 4 MB)
- Questions and answers generated with Groq through LangChain
- One try per IP address, enforced on the server (Upstash Redis on Vercel)
- Download the results as CSV

## Tech stack

FastAPI, LangChain, Groq, Upstash Redis, HTML/CSS/JavaScript, deployed on Vercel.

## Run locally

1. Clone the repo and install the packages:

   ```
   pip install -r requirements.txt
   ```

2. Create a `.env` file in the project root:

   ```
   GROQ_API_KEY=your_key_here
   DISABLE_RATE_LIMIT=1
   ```

   `DISABLE_RATE_LIMIT=1` turns off the one-try limit for local testing only.

3. Start the app:

   ```
   uvicorn app:app --reload
   ```

4. Open http://127.0.0.1:8000

## Deploy on Vercel

1. Push the repo to GitHub and import it in Vercel.
2. Add `GROQ_API_KEY` under Settings, Environment Variables.
3. Add an Upstash Redis database under Storage and connect it to the project.
4. Redeploy.

## Notes

This is a portfolio project. Each visitor can generate once, so the demo stays within free API limits.