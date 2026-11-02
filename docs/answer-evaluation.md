# Answer evaluation

The answer evaluation measures how good chat's answers are. It asks every question of the evaluation set (`eval/retrieval.toml`) on each chat model, and saves the answers with their citations. You then grade each answer on a local page, and a summary compares the models. Ragas scores are an opt-in extra. You run it by hand, on your own machine. It never runs in CI.

Grade again after each change that can affect answers, such as a new prompt or new search settings. An answer that reads the same and cites the same passages as a graded answer keeps its grade, so you grade only the answers that changed.

## Run it

Start your normal stack with the real providers. Then load your keys into the shell and run:

```bash
docker compose up -d --build --wait
set -a; source ~/.config/librag/live.env; set +a
scripts/eval-answers run            # add --ragas for the Ragas scores
scripts/eval-answers grade
scripts/eval-answers summary
```

`run` does these steps:

1. It reads the evaluation set and the chat models from `GET /api/config/models`.
2. It refuses to start when a key is missing from the shell. Each chat model's provider needs its key (`OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, `GEMINI_API_KEY` or `XAI_API_KEY`). `--ragas` also needs `OPENAI_API_KEY` for the judge.
3. It uploads and indexes the evaluation books that are missing, as `scripts/eval-retrieval` does.
4. It asks each question on each model through `POST /api/chat`, limited to the evaluation books.
5. With `--ragas`, it scores each answer right after it arrives.
6. It writes `eval-reports/answers-<timestamp>.json` and prints the usage table per model.
7. It deletes the books that it uploaded, unless you give `--keep-books`.

A run of the 25 questions on 2 models makes 50 chat requests. Each answer also costs up to 5 Ragas calls and 2 embedding calls with `--ragas`.

| Command or variable | Effect |
|---|---|
| `scripts/eval-answers run --ragas` | Adds Ragas faithfulness and answer relevancy to each answer. GPT 6.1 Terra judges both models' answers. |
| `scripts/eval-answers run --keep-books` | Keeps the evaluation books in the library after the run. |
| `scripts/eval-answers grade [report]` | Serves the grading page for the report on http://127.0.0.1:8010 and opens it. The default is the newest report. `--port` changes the port; `--no-browser` does not open the page. |
| `scripts/eval-answers summary [report]` | Prints the summary of the report. The default is the newest report. |
| `LIBRAG_LIVE_BUDGET_USD` | The cost cap of the run, in dollars. The default is 2. |
| `LIBRAG_EVAL_URL` | The stack to ask. The default is `http://localhost:8000`. |

### The cost cap

The run checks the cap before each chat request and before each Ragas judgement. The known cost counts chat and Ragas together. When it reaches `LIBRAG_LIVE_BUDGET_USD`, the run stops, saves the answers it has, and says that it reached the budget. A judgement makes several calls, so the last one can pass the cap by a few cents.

A cost is unknown when LiteLLM has no price for the model. The table then shows "unknown", and the cap does not count that cost.

A failed chat request or a failed Ragas judgement also stops the run, and the command exits with 1. The report keeps every answer that chat returned. An answer whose judgement failed or would pass the cap has no Ragas scores.

## The report

Each answer in `eval-reports/answers-<timestamp>.json` holds:

- the question ID, its type and its text, and the model;
- the answer parts (book claims, synthesis, general) with their citation numbers;
- the cited passages, with book, chapter, section and text;
- the evidence check;
- the usage: input and output tokens, cost and latency;
- the Ragas scores, or `null` without `--ragas`;
- the answer hash, which grades use to find the answer again.

The **evidence check** uses the quote matcher of the retrieval evaluation. For each evidence quote, `cited_in` lists the citations whose passage holds the quote. The check passes when every quote is in a cited passage. A negative question has no quotes: its check passes when the answer makes no book claims.

The **Ragas scores** go from 0 to 1:

- **Faithfulness** is the share of the answer's statements that the passages in the answer's prompt support. It is `null` when the prompt held no passages.
- **Answer relevancy** is how well the answer fits the question. Ragas writes questions from the answer and compares them with the real question.

## Grade

`scripts/eval-answers grade` shows one card per question and model. A card shows the question and its type, the answer, each cited passage, the evidence check, and the Ragas scores. Cards that still need a grade come first.

Each choice saves to `eval-reports/grades.json` at once. A reload shows the saved grades. Git ignores the folder, so the grades stay on your machine.

| Grade | Meaning |
|---|---|
| Quality 5 | Complete and correct. Nothing to add. |
| Quality 4 | Correct, with a small gap or a little noise. |
| Quality 3 | Partly right. It misses a key point or adds a wrong detail. |
| Quality 2 | Mostly wrong or off the question, with something useful. |
| Quality 1 | Wrong, empty, or a refusal of a question the books answer. |
| Citations: correct | Each book claim cites passages that support it. |
| Citations: partly correct | Some citations support their claim, and some do not or are missing. |
| Citations: wrong | The citations do not support the claims. |

For a negative question, a good answer says that the books do not answer it. Grade its quality on that. Its citations are correct when it cites nothing for a claim the books do not make.

Notes are optional. Use them to say why you gave a low grade.

A card is **carried over** when its answer has the same text and the same cited passages as an answer you graded in an earlier report, for the same question and model. It needs no new grade. A change to a carried-over grade saves it for the current report.

## Summary

`scripts/eval-answers summary` prints one block per model:

- the number of answers, how many still need a grade, and how many were carried over;
- the mean quality grade;
- the share of correct, partly correct and wrong citation grades;
- the share of answers that passed the evidence check;
- the mean Ragas faithfulness and answer relevancy;
- the Ragas agreement.

The **Ragas agreement** is the Spearman correlation over the graded answers. It compares faithfulness with the citation grade (wrong 0, partly 0.5, correct 1), and answer relevancy with the quality grade. A value near 1 means that Ragas ranks the answers as you do. The summary shows "none" with fewer than 2 pairs, or when all values on one side are equal.
