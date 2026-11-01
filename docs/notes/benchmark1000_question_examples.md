# Current question examples and distribution — 2026-11-01

These examples were read from saved artifacts. The combined candidate inventory is 3,774 under current proof-path deduplication: `pool_v1` plus `branch_v1_admission` plus the unwrapped contrast members. This is not the final balanced 1,000-item benchmark. A set of pages, ordered sequence of pages, and character-image multiple choice are distinct formats.

| Answer format | Candidates | Share |
|---|---:|---:|
| Count | 2,613 | 69.2% |
| Text-count comparison (`more`/`fewer`/`same`) | 636 | 16.9% |
| Page position | 278 | 7.4% |
| Character name | 228 | 6.0% |
| Ordered page sequence | 12 | 0.3% |
| Boolean | 4 | 0.1% |
| Set of pages | 3 | 0.1% |
| Total | 3,774 | 100% |

These are answer-format counts, not measured difficulty counts. A count answer can require quote→speaker→appearances traversal. Roughly 86% of the current inventory produces counts or text-count comparisons. All current candidates are template-worded; final family balancing and Qwen wording/synthesis remain pending.

## Verbatim saved examples

### Direct count — My Hero Academia c001

Question: How many text regions are shown on page 2?

Answer: `4`.

### Comparison — Jujutsu Kaisen c002

Question: Compared with page 5, does page 3 contain more text regions, fewer, or the same number?

Answer: `fewer`.

### Character constraints across pages — My Hero Academia c001

Question: Which named character is drawn on page 9 and is drawn on page 3?

Answer: `Giant Villain`.

### Quote to speaker — Blue Exorcist c002

Question: Who is the speaker of the text region reading "he was cool." on page 46?

Answer: `Rin`.

### Next appearance — Blue Exorcist c002

Question: After Rin appears on page 5, on which later page is this character next drawn?

Answer: `6`.

### Quote to speaker to depiction count — Hunter x Hunter c001

Question: How many depictions of the speaker of the text region reading "you are king of the forest, kon... and i don't want that to change." on page 25 appear on that same page?

Answer: `4`.

### Successive speaking searches — Assassination Classroom c001

Question: Identify the speaker of the text "nice to meet you." on page 11. Search only the inclusive range from page 12 to page 21. Start immediately before this range and follow the current person to their next speaking page two times. Keep following the same person. Each new search starts strictly after the page just found. Which page does the final step reach?

Answer: `15`. This example has two navigations; its saved measured primary group is `short`, not a claimed three-hop chain.

### Character-switch chain — Blue Exorcist c002

Question: Identify the speaker of the text "welcome to true cross academy." on page 6. Search only the inclusive range from page 17 to page 26. Start immediately before this range and follow the current person to their next speaking page two times. After each step except the last, switch to the only different character drawn on the page just found. Each new search starts strictly after the page just found. Which page does the final step reach?

Answer: `18`. Its saved group is `chain`; the dependency includes navigation, identity switch and another navigation.

### Shared page set — Hell's Paradise c001

Question: Identify the speakers of the texts "i'm losing my edge, even." on page 15 and "you must first travel to the other side." on page 50, respectively. Search only the inclusive range from page 53 to page 62. List all pages in this range on which both people are drawn.

Answer: `[53, 57, 58, 59, 60, 61, 62]`.

### Gap between resolved speakers' pages — Blue Exorcist c002

Question: Identify the speakers of the texts "...it was you, big brother." on page 40 and "he died protecting me." on page 47, respectively. Search only the inclusive range from page 53 to page 56. Find each person’s first speaking page in this range. How many pages lie strictly between those two pages?

Answer: `1`.

### Parallel branch result — Food Wars c002

Question: Identify the speakers of the texts "are you sure you wish to continue?" on page 18 and "so we can make anything we want, right?" on page 18, respectively. Search only the inclusive range from page 20 to page 25. Keep the first and second person’s searches separate. Condition one: for the first person, start immediately before page 20 and find their first speaking page inside the range. Condition two: for the first person, start strictly after the page found in condition one and find that same person’s next speaking page inside the range. Condition three: for the first person, start strictly after the page found in condition two and find that same person’s next speaking page inside the range. Condition four: for the second person, start immediately before page 20 and find their first speaking page inside the range. Condition five: for the second person, start strictly after the page found in condition four and find that same person’s next speaking page inside the range. After both searches finish, give the two distinct final page positions in increasing chapter order.

Answer: `[21, 22]`.

## Contrasts, visual pilots and sentence plans

The two verified contrast pairs contain four member views, with overlaps accounted for in the 3,774 total. Food Wars changes only search-start 19→20: `[20, 21]`→`[21, 22]`. Blue Exorcist c001 changes start 40→41: `[41, 42]`→`[42, 43]`.

The **45 visual-pilot items** remain outside the admitted total pending crop/distractor review. An actual example from Assassination Classroom c001 is:

> Among the four pictured characters, who says \"we are assas- sins.\" on page 49? Answer A, B, C, or D using the labelled option sheet.

Its saved gold answer is `C`; the actual task includes its labelled image sheet. Quotation escapes above are retained from the saved public field.

The **11 sentence plans** are private preparation artifacts, also outside new-candidate counts. An actual Food Wars reference is:

> The first speaker's final speaking page is page 20. The second speaker's final speaking page is page 21. The final pages in chronological order are pages 20 and 21.

These statements are proved for the plan's specific search conditions. No Qwen-generated sentence candidate or unrestricted-prose verification is claimed.

## Review observations

The current inventory is dominated by counts, comparisons and page-number templates. Final balancing, richer-family supply and natural wording still require work. Formatting variety alone does not add new reasoning families.

Example browsing also found a potential fragmented speaker label in an archived Jujutsu Kaisen c001 line-count item: "How many text regions on page 9 have The as their speaker?" (`7`). The label `The` warrants source/human review; this observation does not automatically invalidate or rewrite annotations or source QA. All human review remains pending until the agreed post-Qwen stage.

## Earlier GEN runs are already included

The current combined total includes earlier GEN-1/GEN-2 questions; it does not describe only the recent benchmark1000 additions. The nine-source pool plan explicitly includes all four old runs. Before cross-run deduplication, the imported legacy contributions are GEN-1/v1: 3,477 selected; GEN-2/v1: 120 selected; GEN-2/v2: five selected; GEN-2/v3: 153 retained proof-passing candidates (zero selected under its original selection policy). Those 3,755 source occurrences become 3,640 distinct archived legacy representatives. The combined 3,774 total is 3,640 archived legacy plus 134 distinct native-admitted candidates under current proof-path keys. VERB request copies and rejected/attempted proposals do not add independent QA to this total. Existing output directories remain preserved.

## Actual question lengths — 2026-11-01

Whitespace word counts over the 3,774 deduplicated candidates: 3,659 at 1–40 words; 103 at 41–80; zero at 81–150; 12 at 151–250; zero above 250. The longest is 184 words. Eight distinct candidates have verified long-relational certificates; length alone does not grant this tag. The 11 separate sentence plans reach 196 words and are not added to candidate counts.

A longest Jujutsu Kaisen c001 example identifies the speakers of quotes on pages 35 and 37, restricts search to pages 39–48, follows the first speaker for two next-speaking steps and the second for three, and asks for the final positions in chronological order. Its answer is `[40, 41]`. The certificate has five necessary navigation clauses and five necessary support pages (35, 37, 39, 40, 41), with maximum parallel-branch depth three. It is not a five-hop sequential chain. Current long questions are explicit search instructions; richer narrative/relationship-description questions and Qwen-produced paragraph answers remain pending.
