# Retainer Agreement Builder

A phone-friendly page that shows the Hager & Schwartz, P.A. retainer letter with its blanks fillable in place,
then fills the original PDF and shows the finished pages. It publishes as a Claude artifact.

- `retainer-agreement.html`: the finished page (generated, do not edit by hand)
- `src/template.html`: the page source
- `templates/`: the two fillable PDFs (paid today only, and balance plus trial fee)
- `tools/build.py`: rebuilds the page from the source and the PDFs

## Rebuild

    pip install pypdf reportlab      # and poppler-utils for pdftotext
    python3 tools/build.py

## Notes

- Everything a person types stays in their own browser. Nothing is sent to a server.
- This repository is private. The PDFs are your firm's documents; keep it that way.
- Never commit `.env` files or API keys. `.gitignore` blocks the common ones.
