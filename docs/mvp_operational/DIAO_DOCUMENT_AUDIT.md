# DIAO document audit

Audit date: 2026-09-05

## Source identity

| Field | Verified value |
|---|---|
| Original supplied file | Operator-supplied local attachment `DIAO-PMMG.pdf` |
| Local working copy | `knowledge/diao/DIAO_PMMG.pdf` |
| Size | 3,320,756 bytes |
| SHA-256 | `747B1EE9E50FC799053CD34F00DCE848DF8EB75AB99B73FE9E92967B1CC91ADA` |
| Physical PDF pages | 2,161 |
| Page format | A4, portrait |
| Encryption | None |
| PDF title / author | `DIAO` / `DIAO` |
| Producer | FPDF 1.52 |
| Embedded creation timestamp | 2021-07-20 12:48:58 (PDF metadata) |
| Visible generation timestamp | 20/07/2021 12:48 on page headers |
| Edition/version | Not explicitly identified in the PDF metadata or audited front matter |

The source and working-copy SHA-256 values are identical. The original was not
modified. The working PDF and all local index/extraction directories are covered
by repository ignore rules and must not be published.

## Text-layer audit

Every physical page was inspected programmatically with `pypdf`:

| Measurement | Value |
|---|---:|
| Pages with non-empty extracted text | 2,161 |
| Pages without extracted text | 0 |
| Pages with fewer than 20 extracted characters | 0 |
| Total extracted characters | 3,635,801 |
| Median characters per physical page | 1,614 |
| Minimum / maximum characters | 38 / 3,198 |

The PDF therefore has a usable native text layer and does not require mass OCR.
OCR is reserved only for a future page-specific defect or essential visual
content that cannot be recovered from the text layer. Text extraction must also
normalize occasional legacy FPDF character-map artefacts without changing the
source PDF.

## Structure and pagination

- Physical pages 1-63 form a detailed sumário.
- Physical page 64 begins the printed page 1, `Apresentação`.
- Physical page 65 begins `1 - Aspectos Gerais`.
- Physical page 69 includes `1.3 - Procedimentos Operacionais`.
- Nature entries use an exact code and title, followed by institutional sections
  such as `PELO CENTRO DE OPERAÇÕES / SOU / SOF`, `PELA POLÍCIA MILITAR`,
  `PELA POLÍCIA CIVIL` and `LOCAL DE ENCERRAMENTO` where applicable.
- The printed page number is not identical to the physical PDF page. Both must
  remain in chunk metadata.
- Physical page 2160 carries printed page 2097; physical page 2161 contains only
  the reserved header. This explains the difference between the 2,161 physical
  pages and the final printed page number.

## Visual verification

Rendered samples were inspected from the sumário, presentation, general
procedures, a nature entry and the final section. Text is legible, page numbers
are visible, headings are distinct and no clipping or overlapping content was
observed. Poppler emitted a missing display-font warning for `Symbol`, but the
sampled pages rendered normal text and list markers adequately; retrieval relies
on the native text layer rather than glyph-image recognition.

## Content summary

The document is the Diretriz Integrada de Ações e Operações do Sistema de
Defesa Social de Minas Gerais. It contains general concepts and operational
procedures followed by a large coded catalogue of penal, administrative and
operational natures, with procedures separated by responsible institution and
closing-location guidance. It is appropriate as the real local source for
source-grounded operational retrieval, subject to confirmation of the current
applicable edition by the responsible institution before production use.

## Audit decision

`DIAO_DOCUMENT = PASS`

`DIAO_NATIVE_TEXT_EXTRACTION = PASS`

`MASS_OCR_REQUIRED = NO`

`DIAO_ALLOWED_IN_GIT = NO`
