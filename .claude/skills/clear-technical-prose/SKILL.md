---
name: clear-technical-prose
description: >-
  Writes user-facing explanations, summaries, and procedures in short
  active sentences. One idea per sentence, the result first, technical
  names unchanged. Use when explaining, summarizing, or describing, or
  when the user asks for clearer prose, shorter prose, or Simplified
  Technical English (ASD-STE100).
---

# Clear technical prose

These rules follow ASD-STE100 sentence structure. They ignore its approved-word dictionary.

## Priority

Follow the rules below. Drop a single rule when it makes that sentence harder to understand. Keep the other rules.

## Scope

Use this skill for explanations, summaries, and procedures in the user-facing reply.

Leave these unchanged:

- Fenced code, diffs, file paths, test IDs, and quoted errors
- A format the user requested, such as a commit message, a review, or a table
- The user's words when you quote them
- Safety requirements, citation format, and project code style

## Sentences

- Put the result in the first sentence. That sentence answers the question.
- Put one instruction or one idea in each sentence.
- Join nouns with "and". Start a new sentence for a second instruction, a second idea, or the next step.
- Write a step in 20 words or fewer. Write an explanation in 25 words or fewer. Split a sentence that passes its cap.
- Count a list item as a sentence.
- Use active voice. Name the actor. Use passive voice only when the actor is unknown.
- Use present, past, future, infinitive, or imperative. Describe code in the present tense.
- Use present perfect for a current result. Use "can", "should", "must", and "will".
- Do not stack auxiliaries, as in "would have been".
- Write an "-ing" verb only when the actor is clear. Rewrite a dangling "-ing" clause.
- Keep the subject, the verb, and the articles.
- Split a semicolon into two sentences.

## Words

- Pick one word for a concept and use that word for the whole reply.
- "use", "utilize", and "leverage" are one action. Write "use".
- Use a phrasal verb only when it has one clear meaning. Write "remove" when you mean "take off".
- Prefer the short common word.
- Break a noun stack longer than 3 words. Keep an established technical name whole.
- Give uncertainty in one plain sentence. Name the gap when you did not check.

## Structure

- One topic per paragraph. Maximum 6 sentences.
- Stop when the question is answered.
- Do not add an introduction, restate the question, or close with a summary.
- Use a numbered list for 3 or more steps.
- Use a bulleted list for 3 or more parallel items or conditions.
- Keep one or two items in sentences.

## Technical terms

- Keep product names, API names, code identifiers, and domain terms as written.
- Define a term that is not common English at its first use. Define it once.

## Vocabulary

You may use any clear English word. Use a natural sentence when it still follows the rules above. The reply should sound like a clear person.

## Before you send

1. The first sentence answers the question.
2. Each step is its own sentence. No sentence passes 25 words.
3. The same concept uses the same word.
4. Technical names are unchanged.
5. The reply has no introduction and no closing summary.

## Examples

### Status

Before:
I've gone ahead and updated the account selection hook so that it now handles the case where the loaded account comes back as null, and I also made sure the card doesn't jump around while things are loading.

After:
useAccountSelection now handles a null account. The card keeps its skeleton while the query is loading. The layout stays stable.

### Explanation

Before:
The reason the company section isn't showing up is because useCompanyLookup is still verifying the KVK number and also confirming the billing customer type before it renders the details, which can be confusing.

After:
The company section stays hidden. KVK is the Dutch Chamber of Commerce number. useCompanyLookup waits for a valid KVK number and a billing customer type. The section renders when the KVK number and the billing customer type are valid.

### Procedure

Before:
First you should take off the old token and then set up the new one in the keychain, and after that you can restart the app to confirm everything worked.

After:
Login uses the new token.

1. Remove the old token.
2. Store the new token in the keychain.
3. Restart the app.
4. Check that login succeeds.
