# Course Paper

This directory contains an IEEE-style course paper draft for the CDFD Path Generator project.

## Files

- `main.tex`: paper draft.
- `references.bib`: bibliography entries used by the draft.
- `requirements-summary.md`: Chinese summary of the latest teacher feedback and project requirements.
- `template/`: minimal IEEEtran template files extracted from the CTAN IEEEtran package.

## Template Source

The first attempted download target was the official IEEE conference template page:

```text
https://www.ieee.org/conferences/publishing/templates.html
```

The automated request to the IEEE download gateway was rejected, so the local template files were taken from the CTAN IEEEtran package instead:

```text
https://ctan.org/pkg/ieeetran
```

CTAN describes `IEEEtran` as a document class for IEEE transactions, journals, and conferences. The package is also included in TeX Live and MiKTeX.

## Build

Local PDF compilation requires a TeX Live or MiKTeX installation with `pdflatex`, `bibtex`, and `latexmk` available. The bundled Tectonic binary is not used for this project because the draft uses bibliography tooling.

From this directory:

```bash
pdflatex main.tex
bibtex main
pdflatex main.tex
pdflatex main.tex
```

Overleaf can compile the same files directly. Upload `main.tex`, `references.bib`, and the `template/` directory, or select Overleaf's IEEE Conference Template and copy the content of `main.tex`.
