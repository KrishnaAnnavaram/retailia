# ASD-STE100 Simplified Technical English: the text standard

The `README.md` of retailia and this guide use these rules. Section 1 and Section 2 are the
general rules. Section 3 is the **project vocabulary**: the technical names and the technical verbs
of retailia, each with one meaning. If you change the README, use these rules and these terms.

## 1. Rules for the text

### Words

1. Use one word for one meaning, and one meaning for one word. Do not use synonyms for variety.
2. Use a word only as one part of speech. For example, "test" is a noun or a verb, "check" is a verb.
3. Do not use phrasal verbs (`set up`, `carry out`, `find out`, `pick up`, `look up`, `come up with`).
   Use one verb: "prepare", "do", "find", "get", "make".
4. Do not use an "-ing" form as a noun or an adjective ("the running job", "after indexing").
   Exception: a technical name, a file name, a command or a status value.
5. Do not use contractions (`don't`, `it's`, `can't`). Do not use slang or idioms
   (`out of the box`, `under the hood`, `at a glance`, `gotcha`, `bells and whistles`).
6. Do not use `and/or`. Write "A, B or both".
7. Do not use `should`, `could`, `would` or `may` for instructions. Use "must" for a rule, the
   imperative for a step and "can" for a possibility.
8. Keep the articles "a", "an" and "the" in sentences.
9. Do not make a noun cluster of more than three words. A technical name is one word.

### Sentences

1. A procedural sentence (an instruction) has a maximum of **20 words**.
2. A descriptive sentence has a maximum of **25 words**.
3. Write one instruction in one sentence.
4. Use the imperative for an instruction: "Run the tests." Not `The tests should be run.`
5. Use the active voice. Use the passive voice only when the agent of the action is not important.
6. Use only the simple present, the simple past and the simple future.
7. Put a condition before the instruction: "If the index is stale, build it again."
8. Do not use semicolons in sentences. Write two sentences.

### Paragraphs, notes and warnings

1. A paragraph has one topic and a maximum of **6 sentences**. Start with the topic sentence.
2. A warning or a caution starts with a clear command. Then it gives the reason.
3. A note gives information. It does not give an instruction.
4. Use a vertical list for a sequence or a set of conditions. Each item of a numbered procedure is one step.

### Tables, headings and diagrams

1. A table cell can be a short phrase. If a cell has a sentence, the sentence obeys the rules.
2. A heading is a noun phrase ("The cost model") or an imperative ("Run the demo").
   Do not start a heading with an "-ing" form.
3. A diagram label is a short phrase. Use the same terms as the text.

### What STE does not change

Code, commands, file names, paths, field names, environment variables, status values, enum values,
product names and URLs stay exactly as they are. They are technical names. Put them in backticks.

## 2. General words to replace

| Do not use | Use |
|---|---|
| utilize, leverage | use |
| in order to | to |
| set up | prepare, install, configure |
| carry out, perform | do |
| make sure, ensure | make sure (allowed), or "check that" |
| a lot of, lots of | many, much |
| e.g., i.e. | for example, that is |
| should (instruction) | must (rule) / imperative (step) |
| might, may (possibility) | can |
| very, really, just, simply, easily | (delete) |
| seamless, robust, powerful, blazing | (delete or give a measured fact) |


## 3. Project vocabulary

These terms have one meaning in the README and in this guide. The "Do not use" column lists the
synonyms that the documents do not use for the same meaning.

### 3.1 Technical names (nouns)

| Term | Meaning | Do not use |
|---|---|---|
| **assistant** | The class `Assistant` and the complete retailia program that answers a question | bot, chatbot, agent (alone), AI |
| **customer** | A person with the role `customer` in the `customers` table | user (for a person), client, shopper |
| **staff member** | A person with the role `staff` in the `customers` table | admin, employee |
| **operator** | The person who installs and runs retailia | admin, maintainer |
| **username** | The login name in `customers.username`, for example `customer02` | handle, login, account name |
| **password** | The secret that a customer or a staff member gives at sign-in (minimum 8 characters) | passcode, PIN, secret |
| **demo password** | The one random password that `retailia init-db` makes and prints once for all demo accounts | default password, test password |
| **sign-in** | The check of a username and a password by `AuthService.login` | login (in prose), logon, authentication (in prose) |
| **lockout** | The period in which `login` rejects an account after too many failed sign-ins | ban, block, freeze |
| **principal** | The `Principal` object: `customer_id`, `username`, `role` and `email` of the signed-in person | identity object, user object |
| **role** | `customer` or `staff` | permission level, user type |
| **session token** | The random text that the Streamlit app keeps in the browser to find the principal | cookie, session id |
| **conversation** | The `Conversation` object: one principal and the message history | chat session, thread |
| **question** | One text that the customer or the staff member sends | query, prompt, input |
| **answer** | The `Answer` object, and its text, that the assistant returns for one question | reply, response, output |
| **model** | The chat model that reads the conversation and sends tool requests | LLM (in prose), AI, brain |
| **offline model** | The rule-based model `OfflineModel`. It needs no network and no key | mock, fake, stub, dummy model |
| **hosted model** | A model behind an OpenAI-compatible chat API, remote or local | cloud model, real model, online model |
| **router** | The function `classify` in `agent/router.py` that gives a route for a question | classifier, intent engine |
| **route** | The label of a question: `account`, `catalog`, `faq`, `analytics`, `smalltalk` or `unknown` | category, intent (for the label) |
| **intent** | The sub-label of an `account` route: `order`, `follow_up`, `orders`, `cart`, `account` or `reviews` | route (for the sub-label), action |
| **provider** | The value of `RETAILIA_LLM_PROVIDER`: `offline` or `openai` | backend, vendor, engine |
| **tool** | One of the nine typed functions in `TOOLS` that the model can call | function, action, skill, command |
| **tool request** | One `ToolRequest` from the model to run one tool with arguments | tool call (in prose), invocation |
| **tool result** | The JSON object that a tool returns. It always has a `found` flag | tool output, tool response |
| **account tool** | A tool that reads the data of the signed-in customer through the customer scope | user tool, profile tool |
| **catalog tool** | `search_products` or `get_product`, which read public product data | product tool, shop tool |
| **analytics tool** | `run_catalog_analytics`, the staff-only tool that runs one `SELECT` on the analytics views | SQL tool, report tool |
| **customer scope** | The `CustomerScope` object that adds `customer_id = ?` to each account query | filter, tenant, row filter |
| **catalog** | The public product data: products, categories and average ratings | catalogue (in prose), inventory, shop |
| **analytics view** | One of the three views without personal data: `v_catalog`, `v_product_sales`, `v_orders_by_month` | report table, safe table |
| **authorizer** | The SQLite callback `_authorizer` that allows or denies each part of an analytics query | SQL filter, firewall |
| **step** | One call to the model inside the loop for one question | turn (for model calls), iteration, round trip |
| **step limit** | The maximum number of steps for one question (`RETAILIA_MAX_TOOL_STEPS`) | max iterations, loop limit |
| **guardrail** | A rule in `agent/guardrails.py` that checks a question or an answer | filter, safety layer, moderation |
| **cross-account request** | A question that names other customers, a customer number or bulk personal data | foreign request, data request |
| **refusal** | The fixed answer `CROSS_ACCOUNT_REFUSAL` to a cross-account request | rejection, denial |
| **injection flag** | The `injection_suspected` value on an answer, set by `looks_like_injection` | injection alert, attack flag |
| **FAQ** | The store policy files in `RETAILIA_FAQ_DIR` (`.md`, `.txt` and, with `pypdf`, `.pdf`) | knowledge base, docs |
| **section** | One part of the FAQ: the text under one `##` or `###` heading, or one part of a PDF page | chunk (in prose), document |
| **section id** | The stable id of a section, `<file stem>#<heading slug>`, for example `store_faq#warranty` | chunk id (in prose), key |
| **FAQ index** | The JSON file that `retailia build-index` writes: sections, vectors, embedder name and source hash | vector store, cache |
| **embedder** | The object that changes text into a vector: `hashing-512` or `openai:<model>` | encoder, embedding engine |
| **retriever** | The `HybridRetriever` that scores each section with BM25 and cosine similarity | search engine, ranker |
| **passage** | One section that the retriever returns for a question, with a score | hit, snippet |
| **citation** | A section id in square brackets in an answer, for example `[store_faq#warranty]` | reference, source link, footnote |
| **suite** | One JSONL file of evaluation cases: `routing`, `account_qa`, `faq_qa` or `redteam` | test set, dataset, benchmark |
| **case** | One line in a suite | test case (in prose), sample |
| **red-team case** | One case in `redteam.jsonl` that tries to get data or actions that are not permitted | attack, exploit |
| **evaluation harness** | The module `evaluation/harness.py` that runs all suites and gives a summary | evaluator, benchmark, test runner |
| **fingerprint** | The SHA-256 hash of all store tables (not the login counters), before and after the suites | checksum, snapshot |
| **demo store** | The SQLite file that `retailia init-db` makes with synthetic data | sample data, fixture database |

### 3.2 Technical verbs

| Verb | Meaning |
|---|---|
| **scope** | Add `customer_id = ?` with the id of the principal to an account query |
| **route** | Give a question a route and an intent with the router |
| **validate** | Compare tool-request arguments with the tool fields and reject bad values |
| **retrieve** | Find the passages for a question with the retriever |
| **cite** | Put a section id in square brackets in an answer |
| **redact** | Replace an email address or a different personal value with a fixed marker |
| **seed** | Delete the demo data and write new synthetic customers, products, orders and reviews |
| **index** | Read the FAQ, split it into sections, make vectors and write the FAQ index |
| **lock** | Set `locked_until` on an account after too many failed sign-ins |
| **revoke** | Delete a session token from the session store |
| **trim** | Remove the oldest messages from the conversation at a question boundary |
