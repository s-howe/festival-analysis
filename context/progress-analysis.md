# Progress notes — data analysis

Three notebooks under `analysis/`, reading from the DuckDB views described in
`progress-data.md`.

| Notebook                  | State |
|---------------------------|-------|
| `eda.ipynb`               | Largely complete; final favourite-artists-per-festival pivot built but uncommented |
| `uniqueness.ipynb`        | Core Jaccard machinery built; commentary marked **TBC** |
| `local-heroes.ipynb`      | Complete |

---

## `eda.ipynb`

Wide tour across festivals, editions, artists, lineups.

- **Festivals (134)**: heavy tail toward small; only a handful of `5 - XL`.
- **Editions (1,018)**: Europe-dominated; UK + NL lead absolute counts, Malta/HR/NL lead per-capita. XL festivals cluster around the summer solstice; nothing happens after October. Lockdown dip in 2020–21. Recent growth is in `XS`–`M`.
- **Artists (13,370)**: ~95% of RA's TOP1000 covered. UK dominates DJ exports (>2× next country); UK/NL lead per-capita.
- **Lineups**: festivals mostly book home-grown DJs; HR→UK flow is the strongest cross-country pattern (British-run destination festivals). **Big-hitter top-20 is remarkably static over the last decade** — only Eris Drew, Octo Octa, Peach, Saoirse are genuine newcomers; Gerd Janson, Hunee, Midland, Joy O winding down.

---

## `uniqueness.ipynb`

Pairwise Jaccard similarity between festivals, restricted to the top 500 artists for speed.

- All ~140 festivals: mean Jaccard ≈ **0.05** — festivals are mostly unique.
- Top 50 by booking volume: mean Jaccard ≈ **0.16** — big festivals share a lot more.
- Drilldowns done: Horst × Dekmantel, Houghton × Gottwood, Gala 2026 × Lentekabinet 2026.
- Next: per-festival uniqueness score, write up the top pairs.

---

## `local-heroes.ipynb`

Home-country booking share over 49,547 bookings.

- UK has the highest home share; NL/FR/DE/BE/ES sit lower and similar.
- **Croatia is the standout low outlier** — UK-run destination festivals; some HR editions booked zero Croatian artists.
- Top-20 festivals by home share are almost entirely British.
- Home-share drops monotonically with size (HR excluded): **XS 50% → S 46% → M 44% → L 34% → XL 31%**. Bigger budgets buy more international bookings.

---

## Cross-cutting

UK↔HR booking flow and big-hitter inertia + high inter-similarity of large festivals point at the same story: a small core of artists is shared across the top tier.

---

## Next

**In-flight**
- Finish EDA's favourite-artists-per-festival cell (commentary + viz).
- Replace `TBC` in uniqueness with a write-up and a per-festival uniqueness score.

**From `rough-plan.md`, not started**: tipping-point festivals, artist career arc, cultural exporters, freshness, taste-makers, network graphs (festival similarity, artist co-booking, bipartite, year-by-year evolution).

**Blocked**: gender / race diversity — columns exist on `artists` but are empty.
