One of the main things, when doing questions, where we are using names of charcters from ground truth, and name appear in question or answer, we have to make sure that name appear somewhere in chapter, so model can answer it, other wise it does not make any sense to have that question.
Answers must not be easy to guess (2026-10-23). Character-name answers are fine, but at most ~30% of
them may be the chapter's most frequent characters (a model can guess "the main character"). Avoid
yes/no, left/right and other two-option answers (50% by chance), keeping them to a ~5% share. Prefer open
answers: names, pages/panels, counts, objects/actions, lists. Rules in docs/specs/05, 07 and 09.
