# Search-link source templates

Source: Google Sheets `1YSrArkAufuFCT7Nmm7wofYKvfnVe0Xg5_Egbui4futM`, gid `1295156649`, row 9.
Captured: 2026-08-09 from `/tmp/sheet.xlsx`.

`{q}` is the URL-encoded species query string. Each template is the literal HYPERLINK URL with `{q}` in place of the species name (and Sheet's `&B9&` cell reference replaced by `{q}`).

| Source       | URL template |
| ------------ | ------------ |
| Wikipedia    | `http://es.Wikipedia.org/wiki/Special:Search?search={q}` |
| Google       | `http://Google.com/search?q={q}` |
| BHL          | `http://biodiversitylibrary.org/search?SearchTerm={q}` |
| ResearchGate | `http://researchgate.net/search?q={q}` |
| Plos         | `http://journals.plos.org/plosone/search?filterJournals=PLoSONE&q={q}&page=1` |
| Academia     | `http://academia.edu/people/search?utf8=%E2%9C%93&q={q}` |
| Scielo       | `http://search.scielo.org/?q={q}` |
| Scholar      | `http://scholar.google.com/scholar?hl=es&as_sdt=0%2C5&q={q}&btnG=` |
| Youtube      | `http://youtube.com/results?search_query={q}` |
| Zootaxa      | `http://mapress.com/j/zt/search/search?query={q}` |
| Photos       | `https://www.google.com/search?q={q}&newwindow=1&sca_esv=2e6c317c12a55098&udm=2&sxsrf=APpeQnsW3m8Kyq1XRFki6S6zTiFUL-7OkQ:1786299735760&source=lnt&tbs=isz:l&sa=X&ved=2ahUKEwjL9tiJlZSWAxUWFLkGHas8AI8QpwV6BAgIEAY&biw=1728&bih=963&dpr=2` |
| Sci-hub      | `https://sci-hub.ru/match/{q}` (substitutes species) |

## Notes
- Most sources use `http://` (HTTP). The Photos URL is the only one already on HTTPS.
- `Photos` URL is the literal Google Images search URL from cell M9 of the sheet. It contains tracking params that may go stale; preserved for parity. If parity becomes optional, replace with `https://www.google.com/search?q={q}&tbm=isch`.
- Species name must be URL-encoded with `urllib.parse.quote_plus(species, safe='')` so spaces become `+` and special chars are percent-encoded.
