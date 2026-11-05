# Local browser assets

These exact releases replace the render-blocking cdnjs / Google Fonts requests
in the shared page layout. They are served and cache-versioned by the app's own
WhiteNoise static-file pipeline; no new runtime service or JavaScript dependency
is introduced.

| Package | Version | Source | License |
|---|---|---|---|
| bootstrap | 5.3.2 | `registry.npmjs.org/bootstrap/-/bootstrap-5.3.2.tgz` | MIT, `bootstrap/LICENSE` |
| bootstrap-icons | 1.11.3 | `registry.npmjs.org/bootstrap-icons/-/bootstrap-icons-1.11.3.tgz` | MIT, `bootstrap-icons/LICENSE` |
| @fontsource/inter | 5.2.5 | `registry.npmjs.org/@fontsource/inter/-/inter-5.2.5.tgz` | SIL OFL 1.1, `fonts/Inter-LICENSE` |
| @fontsource/fraunces | 5.2.5 | `registry.npmjs.org/@fontsource/fraunces/-/fraunces-5.2.5.tgz` | SIL OFL 1.1, `fonts/Fraunces-LICENSE` |

Only the used Bootstrap bundle, icon fonts, and Latin WOFF2 font weights are
included. `fonts/fonts.css` is a small local face declaration using those files.
Other scripts fall back to the system font, as before. Bootstrap's source maps
are included so the production manifest can resolve its sourceMappingURL links.

To update, download the chosen npm release, verify its published integrity,
replace the corresponding files and licenses together, and run the static-manifest
regression in `students/test_result_performance.py` before deploying. Do not edit
the minified distributions in place.
