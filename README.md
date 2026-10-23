# EURO 2025 Player Comparison Lab

Public-data football research demonstration. No club-system connection or private club data.

Deploy on Streamlit Community Cloud with entrypoint `streamlit_app.py`, Python 3.12.
Install dependencies from `requirements.txt`. All 31 match event files are included as
lossless gzip files. No data download is required at startup. Data may take several
seconds to aggregate on first use.

## Attribution
Data: Hudl StatsBomb Open Data, https://github.com/statsbomb/open-data .
The original event JSON bytes are preserved by lossless compression. Source URLs and
SHA256 checksums are in research/euro-demo/manifest.json. Provider data remains subject
to the StatsBomb open-data licence: https://github.com/statsbomb/open-data/blob/master/LICENSE.pdf .
Derived metrics and phase rules are research implementations, not verified club formulas.
See the in-app Methodology and Data & exports tabs for limitations and source links.
