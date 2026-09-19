# কীভাবে একটি নতুন সেশনে প্রম্পট শুরু করবেন (START-গাইড)

_উদ্দেশ্য: আগের কথোপকথন মনে নেই এমন নতুন agent-সেশনে যেকোনো নম্বরের প্রম্পট ঠিক জায়গা থেকে শুরু করা।_

## ১. মাত্র দুইটি জিনিস পাঠাবেন

1. **START-ব্লক** — `docs/prompts/copy-paste/kickoff/prompt-<NN>-START.txt` (সংখ্যা-ভরা, তৈরি করা)। জেনেরিক সংস্করণ §৩-এ।
2. **প্রম্পট ফাইল** — `docs/prompts/copy-paste/prompt-<NN>-*.txt` (বা `docs/prompts/prompt-<NN>-*.md`) — এটাই কাজের স্পেক: চাহিদা, ধাপ, সীমা, টেস্ট কমান্ড, PR+CI, ডক আপডেট, owner-প্রশ্ন।

> ব্যস। আর কিছু লিখতে/বুঝিয়ে দিতে হয় না — বাকি সব **repo-তেই আছে**, এজেন্ট নিজে পড়ে ও যাচাই করে।

## ২. কেন এতটুকুই যথেষ্ট (তিন-ভাগের চুক্তি)

| কী | কোথায় থাকে | কে দেয় |
|---|---|---|
| কাজের স্পেক (কী করতে হবে) | `docs/prompts/prompt-NN-*.md` | আপনি (কপি-পেস্ট) |
| অবস্থা (কোন প্রম্পট শেষ, commit/PR, কী যাচাই হয়েছে, কী বাকি) | `docs/prompts/PROGRESS.md` + `docs/prompts/reports/*.md` | repo — এজেন্ট পড়ে **নিজে প্রমাণ করে** |
| owner-সিদ্ধান্ত (নীতি/সংখ্যা/অনুমোদন) | `docs/prompts/README.md` §৭ + reports + আপনার মেসেজের ফাঁকা ঘর | আপনি (থাকলে) |

তিনটিই থাকলে নতুন সেশনে "কোথায় আছি" হারায় না।

## ৩. জেনেরিক START-ব্লক (যেকোনো প্রম্পটে ব্যবহারযোগ্য)

`<NN>`, `<SID>`, `<TITLE>`, `<PREV>` পূরণ করলেই চলে; `copy-paste/kickoff/`-এ প্রতিটি প্রম্পটের **আগেই পূরণ করা** সংস্করণ আছে।

```text
▶ নতুন সেশন — প্রম্পট <০N> / ২৮ (সেশন <সেশন আইডি> · <শিরোনাম>)

আমি একটি নতুন agent-সেশনে আছি; তোমার আগের কথোপকথনের কিছু মনে নেই। নিয়ম:

১. আগে শুধু পড়ো (কোনো ফাইল বদলানোর আগে):
   - `docs/prompts/PROGRESS.md` — কোন প্রম্পট শেষ (✅/🟡/⛔), তাদের commit/PR ও নোট
   - `docs/prompts/README.md` §৭ — owner-সিদ্ধান্তের সারি
   - `docs/prompts/reports/` — আগের সব সেশনের রিপোর্ট — আগের সেশনের প্রকৃত ফল, ঝুঁকি ও যাচাই-না-হওয়া অংশ
   - `docs/prompts/reports/০০.md` — baseline verdict (কোনটি ইতিমধ্যেই আছে)
   - `docs/prompts/prompt-<NN>-*.md` — এটাই তোমার কাজের স্পেক (ধাপ, সীমা, কমান্ড, PR, ডক)
২. তারপর যাচাই করো (দাবি নয়, প্রমাণ): `git log --oneline -12`, `git status -sb`,
   `git rev-parse HEAD origin/main`। প্রম্পট ০১…<আগের নম্বর> ✅ হলে তাদের কাজ এই branch-এ আছে কি না দেখো।
   → ⚠️ আগের প্রম্পট 🟡/⛔ হলে বা commit না থাকলে **কাজ শুরু করবে না**; এক লাইনে জানাও কী অনুপস্থিত।
   → (ব্যতিক্রম: নিচে আমি লিখে দিলে) <থাকলে লিখুন: আগের প্রম্পট আমি অন্য সেশনে করেছি — যাচাই করে স্ট্যাটাস বসাও>
৩. owner-সিদ্ধান্ত: নিচে আমি যা লিখেছি সেটাই চূড়ান্ত। খালি থাকলে prompt-এর §৮-এর প্রশ্নগুলোর উত্তর
   আগে repo-তে খোঁজো (README §৭, reports) — না পেলে সংক্ষেপে প্রশ্ন করো, বানিয়ে কিছু ধরে নিও না।
   --- owner-সিদ্ধান্ত (থাকলে এখানে লিখুন; না থাকলে ফাঁকা রাখুন): __DECISIONS__
   ---
৪. এরপর prompt-এর §০ অনুযায়ী শুরু করো — প্রথম লাইনে স্ট্যাটাস ব্লক:
   `▶ চলছে: প্রম্পট <NN> / ২৮ (prompt <NN>/28) — সেশন <সেশন আইডি> · ...`
   এবং prompt-এর §৩–§৯ হুবহু মানো (ধাপ, টেস্ট কমান্ড, PR+CI, ডক/ledger আপডেট, আউটপুট ফরম্যাট)।
৫. শেষে: `docs/prompts/PROGRESS.md`-এ প্রম্পট <০N>-এর সারি আপডেট (স্ট্যাটাস · তারিখ · commit · PR ·
   টেস্ট সংখ্যা) + `docs/prompts/reports/<সেশন আইডি>.md` লিখো + `✔ শেষ হয়েছে: প্রম্পট <০N> / ২৮ …` ব্লক দেখাও।
৬. নিষেধ (prompt-এর §৪-এ বিস্তারিত): branch `arena/01a0b7f7-school-management-system` ছাড়া অন্য কোথাও নয় ·
   `main`-এ push নয় · owner অনুমোদন ছাড়া merge নয় · production DB/live Render/credential ছোঁবা না ·
   SSC Registration পুনরুদ্ধার নয় · migration-এর operations edit নয় · `.env`/`db.sqlite3`/`media/`/`backups/` commit নয়।

```

## ৪. প্রতিটি প্রম্পটের START ফাইল ও আগে-পড়ার তালিকা

| # | সেশন | START ফাইল | আগের যে রিপোর্টগুলো পড়া দরকার | §৮-এ owner-প্রশ্ন |
|---|---|---|---|---|
| 01 | ০০ | `copy-paste/kickoff/prompt-01-START.txt` | `docs/prompts/reports/` (আগের কোনো সেশন নেই) | 2টি |
| 02 | EX-01 | `copy-paste/kickoff/prompt-02-START.txt` | `docs/prompts/reports/০০.md` | 2টি |
| 03 | EX-02 | `copy-paste/kickoff/prompt-03-START.txt` | `docs/prompts/reports/EX-01.md` | 2টি |
| 04 | EX-03 | `copy-paste/kickoff/prompt-04-START.txt` | `docs/prompts/reports/EX-02.md` | 3টি |
| 05 | EX-04 | `copy-paste/kickoff/prompt-05-START.txt` | `docs/prompts/reports/EX-03.md` | 3টি |
| 06 | EX-05 | `copy-paste/kickoff/prompt-06-START.txt` | `docs/prompts/reports/EX-04.md` | 3টি |
| 07 | EX-06 | `copy-paste/kickoff/prompt-07-START.txt` | `docs/prompts/reports/EX-05.md` | 3টি |
| 08 | EX-07 | `copy-paste/kickoff/prompt-08-START.txt` | `docs/prompts/reports/EX-06.md` | 3টি |
| 09 | OF-01 | `copy-paste/kickoff/prompt-09-START.txt` | `docs/prompts/reports/EX-07.md` | 2টি |
| 10 | OF-02 | `copy-paste/kickoff/prompt-10-START.txt` | `docs/prompts/reports/OF-01.md` | 2টি |
| 11 | OF-03 | `copy-paste/kickoff/prompt-11-START.txt` | `docs/prompts/reports/OF-02.md` | 2টি |
| 12 | OF-04 | `copy-paste/kickoff/prompt-12-START.txt` | `docs/prompts/reports/OF-03.md` | 3টি |
| 13 | OF-05 | `copy-paste/kickoff/prompt-13-START.txt` | `docs/prompts/reports/OF-04.md` | 3টি |
| 14 | OF-06 | `copy-paste/kickoff/prompt-14-START.txt` | `docs/prompts/reports/OF-05.md` | 3টি |
| 15 | OF-07 | `copy-paste/kickoff/prompt-15-START.txt` | `docs/prompts/reports/OF-06.md` | 3টি |
| 16 | OF-08 | `copy-paste/kickoff/prompt-16-START.txt` | `docs/prompts/reports/OF-07.md` | 3টি |
| 17 | DB-01 | `copy-paste/kickoff/prompt-17-START.txt` | `docs/prompts/reports/OF-08.md` | 3টি |
| 18 | DB-02 | `copy-paste/kickoff/prompt-18-START.txt` | `docs/prompts/reports/DB-01.md` | 3টি |
| 19 | DB-03 | `copy-paste/kickoff/prompt-19-START.txt` | `docs/prompts/reports/DB-02.md` | 3টি |
| 20 | DB-04 | `copy-paste/kickoff/prompt-20-START.txt` | `docs/prompts/reports/DB-03.md` | 3টি |
| 21 | DB-05 | `copy-paste/kickoff/prompt-21-START.txt` | `docs/prompts/reports/DB-04.md` | 4টি |
| 22 | DB-06 | `copy-paste/kickoff/prompt-22-START.txt` | `docs/prompts/reports/DB-05.md` | 3টি |
| 23 | AT-01 | `copy-paste/kickoff/prompt-23-START.txt` | `docs/prompts/reports/DB-06.md` | 3টি |
| 24 | AT-02 | `copy-paste/kickoff/prompt-24-START.txt` | `docs/prompts/reports/AT-01.md` | 3টি |
| 25 | EM-01 | `copy-paste/kickoff/prompt-25-START.txt` | `docs/prompts/reports/AT-02.md` | 3টি |
| 26 | EM-02 | `copy-paste/kickoff/prompt-26-START.txt` | `docs/prompts/reports/EM-01.md` | 6টি |
| 27 | EM-03 | `copy-paste/kickoff/prompt-27-START.txt` | `docs/prompts/reports/EM-02.md` | 4টি |
| 28 | FN-01 | `copy-paste/kickoff/prompt-28-START.txt` | `docs/prompts/reports/` — বিশেষভাবে `docs/prompts/reports/০০.md` … `docs/prompts/reports/EM-03.md` (27টি রিপোর্ট: সব আগের সেশন) | 3টি |

## ৫. উদাহরণ: প্রম্পট ০৪ (EX-03) পুরো START-ব্লক

```text
▶ নতুন সেশন — প্রম্পট ০৪ / ২৮ (সেশন EX-03 · Group-based Mark Evaluation)

আমি একটি নতুন agent-সেশনে আছি; তোমার আগের কথোপকথনের কিছু মনে নেই। নিয়ম:

১. আগে শুধু পড়ো (কোনো ফাইল বদলানোর আগে):
   - `docs/prompts/PROGRESS.md` — কোন প্রম্পট শেষ (✅/🟡/⛔), তাদের commit/PR ও নোট
   - `docs/prompts/README.md` §৭ — owner-সিদ্ধান্তের সারি
   - `docs/prompts/reports/EX-02.md` — আগের সেশনের প্রকৃত ফল, ঝুঁকি ও যাচাই-না-হওয়া অংশ
   - `docs/prompts/reports/০০.md` — baseline verdict (কোনটি ইতিমধ্যেই আছে)
   - `docs/prompts/prompt-04-*.md` — এটাই তোমার কাজের স্পেক (ধাপ, সীমা, কমান্ড, PR, ডক)
২. তারপর যাচাই করো (দাবি নয়, প্রমাণ): `git log --oneline -12`, `git status -sb`,
   `git rev-parse HEAD origin/main`। প্রম্পট ০১…০৩ ✅ হলে তাদের কাজ এই branch-এ আছে কি না দেখো।
   → ⚠️ আগের প্রম্পট 🟡/⛔ হলে বা commit না থাকলে **কাজ শুরু করবে না**; এক লাইনে জানাও কী অনুপস্থিত।
   → (ব্যতিক্রম: নিচে আমি লিখে দিলে) —
৩. owner-সিদ্ধান্ত: নিচে আমি যা লিখেছি সেটাই চূড়ান্ত। খালি থাকলে prompt-এর §৮-এর প্রশ্নগুলোর উত্তর
   আগে repo-তে খোঁজো (README §৭, reports) — না পেলে সংক্ষেপে প্রশ্ন করো, বানিয়ে কিছু ধরে নিও না।
   --- owner-সিদ্ধান্ত (থাকলে এখানে লিখুন; না থাকলে ফাঁকা রাখুন): __DECISIONS__
   ---
৪. এরপর prompt-এর §০ অনুযায়ী শুরু করো — প্রথম লাইনে স্ট্যাটাস ব্লক:
   `▶ চলছে: প্রম্পট 04 / ২৮ (prompt 04/28) — সেশন EX-03 · ...`
   এবং prompt-এর §৩–§৯ হুবহু মানো (ধাপ, টেস্ট কমান্ড, PR+CI, ডক/ledger আপডেট, আউটপুট ফরম্যাট)।
৫. শেষে: `docs/prompts/PROGRESS.md`-এ প্রম্পট ০৪-এর সারি আপডেট (স্ট্যাটাস · তারিখ · commit · PR ·
   টেস্ট সংখ্যা) + `docs/prompts/reports/EX-03.md` লিখো + `✔ শেষ হয়েছে: প্রম্পট ০৪ / ২৮ …` ব্লক দেখাও।
৬. নিষেধ (prompt-এর §৪-এ বিস্তারিত): branch `arena/01a0b7f7-school-management-system` ছাড়া অন্য কোথাও নয় ·
   `main`-এ push নয় · owner অনুমোদন ছাড়া merge নয় · production DB/live Render/credential ছোঁবা না ·
   SSC Registration পুনরুদ্ধার নয় · migration-এর operations edit নয় · `.env`/`db.sqlite3`/`media/`/`backups/` commit নয়।

```

## ৬. বাস্তবে যা ঘটবে

1. এজেন্ট `PROGRESS.md` পড়ে দেখবে প্রম্পট ০১–০৩-এর অবস্থা; `git log` দিয়ে commit মিলিয়ে নেবে।
2. `reports/০০.md`, `reports/EX-01.md`, `reports/EX-02.md` পড়ে বুঝবে আগের সেশনে কী বদলেছে (আপনার লিখে দেওয়ার দরকার নেই)।
3. prompt-০৪-এর §০ স্ট্যাটাস ব্লক দিয়ে শুরু করবে, §৩ ধাপ ধরে কাজ করবে, §৫-এর কমান্ড চালাবে।
4. শেষে `PROGRESS.md`-এ প্রম্পট ০৪-এর সারি + `reports/EX-03.md` + PR আপডেট করে `✔ শেষ হয়েছে…` ব্লক দেখাবে।

## ৭. যদি আগের প্রম্পট শেষ না থাকে / আংশিক থাকে

- **আগের প্রম্পট অন্য সেশনে শেষ হয়েছে, কিন্তু PROGRESS.md-এ লেখা হয়নি:** START-ব্লকের ২ নম্বর ধাপের ব্যতিক্রম-লাইনে লিখুন — “প্রম্পট ০১–০৩ আমি অন্য সেশনে করেছি; branch-এ কাজগুলো যাচাই করে PROGRESS.md-এ স্ট্যাটাস বসাও, নতুন করে কোরো না।”
- **আগের প্রম্পট আংশিক/ব্লকড:** আগে সেটিই শেষ করুন, নাহলে এই প্রম্পটের নির্ভরতা ভাঙবে। (নাহলে START-ব্লকের owner-সিদ্ধান্তে লিখে দিন “০৩ আংশিক; বাকি ছিল X — সেটা এড়িয়ে এগোও” এবং ঝুঁকি মেনে নিন।)
- **জরুরি কিছু জানাতে চান (নীতি, সংখ্যা, নাম):** START-ব্লকের ৩ নম্বর ধাপের ফাঁকা ঘরে ২–৪ লাইন লিখুন।

## ৮. সর্বনিম্ন নিরাপদ এক-লাইন (যদি পুরো START ব্লক না পাঠাতে চান)

পুরো START ব্লকের বদলে অন্তত এই এক লাইনটি লিখুন (এতে ঝুঁকি সবচেয়ে কম):

```text
docs/prompts/prompt-04-*.md পড়ে তার §০–§৯ হুবহু মানো। আগে docs/prompts/PROGRESS.md ও
docs/prompts/reports/EX-02.md পড়ে যাচাই করো প্রম্পট ০১–০৩ আসলে শেষ কি না (না হলে শুরু কোরো না, জানাও)।
owner-সিদ্ধান্ত: <থাকলে>। শেষে PROGRESS.md + reports/EX-03.md আপডেট করে স্ট্যাটাস ব্লক দেখাও।
```

**কেন পুরো ব্লক ভালো:** শুধু "প্রম্পট ৪ পড়ে কাজ কর" লিখলে এজেন্ট ফাইল খুঁজে পেলেও (ক) আগের প্রম্পট শেষ কি না
যাচাই না করে ফেলে দিতে পারে, (খ) owner-সিদ্ধান্তের কথা জানে না, (গ) `PROGRESS.md`/report আপডেট করতে ভুলে যেতে পারে।

## ৯. এজেন্টকে থামানোর শর্ত (START-ব্লকে আগেই লেখা থাকে)

- আগের নির্ভরতা ✅ নয় বা commit অনুপস্থিত → **শুরু করবে না**, জানাবে।
- owner-সিদ্ধান্ত ছাড়া কিছু "ধরে নেওয়া" নিষেধ → প্রশ্ন করবে।
- টেস্ট fail / CI fail → স্ট্যাটাস 🟡, লুকাবে না।
