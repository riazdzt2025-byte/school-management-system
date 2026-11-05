# Postgres + S3/R2 + দৈনিক ব্যাকআপ — ধাপে ধাপে (বাংলা)

> **কার জন্য:** প্রতিষ্ঠানের সিস্টেম প্রোডাকশনে (Render) চালানো ব্যক্তির জন্য।
> **কী সমাধান করে:** ৩,৫০০ শিক্ষার্থী ও ২৪০ কর্মীর ডেটা এমনভাবে রাখা, যাতে
> (ক) একসাথে অনেক ব্যবহারকারী কাজ করতে পারে, (খ) রিডিপ্লয়ে ছবি না হারায়,
> (গ) প্রতিদিন স্বয়ংক্রিয় ব্যাকআপ থাকে এবং **রিস্টোর করে দেখা** যায়।
> **সময়:** হাতের কাজ ৩–৫ ঘণ্টা (ধাপ ১–৪), তার সাথে Render-এর বিল্ড/অপেক্ষা।
> "২–৩ দিন" বলার কারণ — যাচাই ও একবার রিস্টোর ড্রিল করতে হয়।

---

## ০. যা যা লাগবে

| জিনিস | কেন | খরচ |
|---|---|---|
| Render অ্যাকাউন্ট (কার্ড লাগে) | ওয়েব সার্ভিস + Postgres + cron | $১৪–২০/মাস |
| Cloudflare অ্যাকাউন্ট (R2) | শিক্ষার্থীর ছবি/ফাইল | ১০ GB পর্যন্ত ফ্রি |
| Healthchecks.io অ্যাকাউন্ট | ব্যাকআপ ব্যর্থ/বন্ধ হলে অ্যালার্ট | ফ্রি |
| ডোমেইন | `ALLOWED_HOSTS` ও HTTPS | বছরে ~৳১,২০০ |

> **আগে যা করতেই হবে:** বর্তমান (SQLite) ডেটার একটি ব্যাকআপ — শুধু নিয়ম হিসেবে নয়,
> নিচের ধাপ ১-এ ডেটা সরাতে হবে বলেই।
>
> ```bash
> python manage.py backup_data --backup-root /tmp/pre-migration --keep 2
> ls -la /tmp/pre-migration/
> ```

---

## ১. ধাপ ১ — PostgreSQL

### ১.১ Render-এ ডেটাবেস তৈরি

1. Render ড্যাশবোর্ড → **New → Postgres**
2. Name: `sms-postgres` · Region: **Singapore** (বাংলাদেশের জন্য সবচেয়ে কাছের)
3. Plan: **Basic-256MB** (ফ্রি প্ল্যান কয়েক মাস পরে expire হয়ে **ডেটা মুছে ফেলে** — শিক্ষার্থীর ডেটার জন্য গ্রহণযোগ্য নয়)
4. Create → তৈরি হওয়ার পর **Connections** থেকে কপি করুন:
   - **Internal Database URL** → ওয়েব সার্ভিসের জন্য (একই region, দ্রুত ও ফ্রি ট্রাফিক)
   - **External Database URL** → নিজের ল্যাপটপ থেকে ডেটা সরানোর জন্য (ধাপ ১.৪)

### ১.২ ওয়েব সার্ভিসে env var বসানো

Render → আপনার web service → **Environment** → Add:

| Key | Value |
|---|---|
| `DATABASE_URL` | Internal Database URL (উপরে কপি করা) |
| `DEBUG` | `False` |
| `SECRET_KEY` | ৫০+ অক্ষরের নতুন কী (`python -c "import secrets;print(secrets.token_urlsafe(50))"`) |
| `ALLOWED_HOSTS` | `school.example.com` (আপনার ডোমেইন) |
| `CSRF_TRUSTED_ORIGINS` | `https://school.example.com` |
| `TRUST_FORWARDED_PROTO` | `True` |
| `USE_X_FORWARDED_HOST` | `True` |
| `RATE_LIMIT_CACHE` | `db` (worker বাড়লে রেট-লিমিট গুণ হয়ে যায় না) |

> `DEBUG=False` করার সাথে সাথেই Django পুরোনো `SECRET_KEY` নিয়ে বুট করতে দেবে না —
> তাই দুটো একসাথে সেট করুন (কোডেই এই সুরক্ষা আছে, `settings.py` দেখুন)।

### ১.৩ ডিপ্লয় ও স্কিমা তৈরি

`scripts/render_start.sh` প্রতিবার বুটে `migrate` চালায়, তাই আলাদা করে কিছু করতে হয় না।
ডিপ্লয়ে দেওয়ার পর যাচাই করুন:

```bash
# Render Shell অথবা নিজের মেশিনে (External URL দিয়ে)
python manage.py showmigrations students | tail -5     # শেষ ৫টি [X] হওয়া উচিত
curl -s https://school.example.com/healthz/            # {"status": "ok", "db": "ok"}
```

### ১.৪ পুরোনো ডেটা (SQLite) → Postgres সরানো

> ⚠️ **সবচেয়ে বেশি ভুল হয় এখানেই।** নতুন Postgres-এ `migrate` শুধু *খালি টেবিল* বানায় —
> শিক্ষার্থী, নম্বর, রিসিট কিছুই আসে না। আর `restore_backup` ইঞ্জিন মিলিয়ে কাজ করে
> (sqlite ব্যাকআপ → sqlite-এ), তাই এটি দিয়ে সরাসরি Postgres-এ রিস্টোর হবে না।
> সঠিক পথ: **dumpdata → loaddata → reset_sequences**।

```bash
# (ক) পুরোনো SQLite থেকে ডেটা বের করা — মেশিনে DATABASE_URL *সেট না থাকলে* sqlite ধরে নেবে
python manage.py dumpdata \
  --natural-foreign --natural-primary \
  --exclude contenttypes --exclude auth.permission \
  --exclude sessions --exclude admin.logentry \
  --indent 2 > /tmp/sms-data.json
ls -lh /tmp/sms-data.json          # সাইজ দেখে নিন: ডেটা সত্যিই এসেছে কি না

# (খ) নতুন Postgres-এ ঢোকানো (External URL)
export DATABASE_URL="postgres://...external..."
python manage.py migrate            # স্কিমা
python manage.py loaddata /tmp/sms-data.json

# (গ) আইডি-র sequence ঠিক করা — এই ধাপ বাদ দিলে নতুন শিক্ষার্থী যোগ করলেই
#     "duplicate key value violates unique constraint" আসবে
python manage.py reset_sequences --dry-run
python manage.py reset_sequences
```

**যাচাই (সংখ্যা মিলিয়ে দেখুন — এটাই আসল প্রমাণ):**

```bash
python manage.py shell -c "
from students.models import Student, ExamMark, MoneyReceipt, Employee
print('students', Student.objects.count())
print('exam marks', ExamMark.objects.count())
print('receipts', MoneyReceipt.objects.count())
print('employees', Employee.objects.count())
"
```

ডিমান্ড করা "লাইভ ডেটা" আলাদা রাখতে চাইলে: migration-এর আগে অ্যাপটি **maintenance**
সময়ে রাখুন (বিকেল/রাতে), নাহলে মাঝপথে নতুন সারি যোগ হলে সেটি মিস হবে।

```bash
# নতুন শিক্ষার্থী যোগ করা যায় কি না — sequence ঠিক আছে কি না তার আসল পরীক্ষা
python manage.py shell -c "
from students.models import Student, Institution
s = Student.objects.create(name='Sequence Test', admission_class='6',
                           institution=Institution.objects.first(),
                           student_id='SEQ-TEST-1', guardian_contact_no='01700000000')
print('created id', s.pk); s.delete(); print('deleted ok')
"
```

---

## ২. ধাপ ২ — ছবি ও ফাইল Cloudflare R2-তে

Render-এর ফ্রি/সাধারণ ডিস্ক স্থায়ী নয় — রিডিপ্লয়ে শিক্ষার্থীর ছবি মুছে যায়।
কোডে `USE_S3` পথটি প্রস্তুত ও টেস্টেড (`docs/FREE_TIER_MEDIA_STORAGE.md`)।

### ২.১ বাকেট ও কী

1. Cloudflare ড্যাশবোর্ড → **R2** → **Create bucket** → নাম: `pkfsc-media`
   (Public access **বন্ধ** রাখুন — শিক্ষার্থীর ছবি সাইনড URL দিয়ে যাবে)
2. **R2 → Manage API Tokens → Create API token** → Permission: **Object Read & Write**
   → Bucket scope: শুধু `pkfsc-media`
3. কপি করুন: **Access Key ID**, **Secret Access Key**, আর **Account ID**
   (endpoint হবে `https://<ACCOUNT_ID>.r2.cloudflarestorage.com`)

### ২.২ ওয়েব সার্ভিসে env var

| Key | Value |
|---|---|
| `USE_S3` | `True` |
| `AWS_STORAGE_BUCKET_NAME` | `pkfsc-media` |
| `AWS_ACCESS_KEY_ID` | (টোকেন) |
| `AWS_SECRET_ACCESS_KEY` | (টোকেন) |
| `AWS_S3_ENDPOINT_URL` | `https://<ACCOUNT_ID>.r2.cloudflarestorage.com` |
| `AWS_S3_REGION_NAME` | `auto` |
| `AWS_LOCATION` | `media` |
| `AWS_S3_QUERYSTRING_EXPIRE` | `86400` (এক দিন — স্কুলের দিনভর প্রিন্ট/প্রিভিউয়ের জন্য) |

> **করবেন না:** `AWS_DEFAULT_ACL=public-read` বা `AWS_S3_PUBLIC_BASE_URL` সেট করা।
> নাবালক শিক্ষার্থীর ছবি পাবলিক হয়ে যাবে; ডিপ্লয় চেক (`students.E012`) এটাই আটকায়:
> ```bash
> python manage.py check --deploy
> ```

### ২.৩ যাচাই

```bash
python manage.py check --deploy          # কোনো E012/E011 সতর্কতা থাকা যাবে না
# ব্রাউজারে: একজন শিক্ষার্থীর প্রোফাইল → ছবি আপলোড → ছবি দেখা যায়?
# ছবির URL-এ signature থাকবে (X-Amz-Signature...), পাবলিক লিংক নয়
```

---

## ৩. ধাপ ৩ — দৈনিক ব্যাকআপ (cron)

দুটি পথ; দুটোতেই **অবজেক্ট স্টোরেজে কপি** বাধ্যতামূলক, কারণ cron-এর কোনো স্থায়ী ডিস্ক নেই।

### ৩.১ পথ ক — Render cron (Python)

`render.yaml`-এ `sms-daily-backup` সার্ভিসটি ঠিক এ কাজের জন্য লেখা আছে
(schedule `30 20 * * *` = বাংলাদেশে রাত ২:৩০)। যে env var-গুলো ড্যাশবোর্ডে বসাতে হবে:

| Key | মানে |
|---|---|
| `DATABASE_URL` | Internal Database URL |
| `P0B_BACKUP_ROOT` | `/tmp/backups` (শুধু স্টেজিং) |
| `BACKUP_ENCRYPTION` | `openssl` (বা `age`) |
| `BACKUP_PASSPHRASE` | শক্তিশালী পাসফ্রেজ — ব্যাকআপ ফাইল লিক হলেও ডেটা পড়া যাবে না |
| `BACKUP_OBJECT_STORAGE_BUCKET` | ব্যাকআপ রাখার বাকেট (ছবির বাকেট থেকে **আলাদা** রাখুন) |
| `BACKUP_OBJECT_STORAGE_ACCESS_KEY` / `_SECRET_KEY` / `_ENDPOINT` | ওই বাকেটের কী |
| `BACKUP_OBJECT_STORAGE_REGION` | `auto` |
| `BACKUP_OBJECT_STORAGE_PREFIX` | `sms-backups` |
| `KEEP_BACKUPS` | `7` (লোকালে কত কপি) |
| `BACKUP_OBJECT_STORAGE_KEEP` | `30` (বাকেটে কত দিন) |
| `HEALTHCHECK_PING_URL` | Healthchecks.io-র চেক URL |

> **গুরুত্বপূর্ণ:** Postgres ব্যাকআপ `pg_dump` দিয়ে হয়। Render-এর Python runtime-এ
> `pg_dump` না থাকলে cron প্রতিবার ব্যর্থ হবে (Healthchecks.io অ্যালার্ট দেবে, কিন্তু
> ব্যাকআপ তৈরি হবে না)। নিশ্চিত পথ — Docker:
> `deploy/backup-cron.Dockerfile` (postgresql-client আগেই বসানো), `render.yaml`-এর
> নিচে কমেন্ট করা উদাহরণটি দেখুন।

### ৩.২ পথ খ — বাইরের scheduler (Render-এর বাইরে)

যেকোনো মেশিনে যেখানে `pg_dump` আছে:

```bash
export DATABASE_URL="postgres://...external..."
export P0B_BACKUP_ROOT=/srv/backups
export BACKUP_ENCRYPTION=openssl BACKUP_PASSPHRASE='...'
export BACKUP_OBJECT_STORAGE_BUCKET=... BACKUP_OBJECT_STORAGE_ACCESS_KEY=...
export BACKUP_OBJECT_STORAGE_SECRET_KEY=... BACKUP_OBJECT_STORAGE_ENDPOINT=...
export HEALTHCHECK_PING_URL="https://hc-ping.com/xxxxxxxx"
./scripts/backup_cron.sh && echo OK
```
crond-এ যোগ করুন: `30 20 * * * cd /srv/sms && ./scripts/backup_cron.sh`

### ৩.৩ Healthchecks.io (৫ মিনিটের কাজ, সবচেয়ে বড় লাভ)

1. Healthchecks.io → **New check** → Period: `1 day` · Grace: `6 hours`
2. Ping URL কপি করে `HEALTHCHECK_PING_URL`-এ বসান
3. **Integrations**-এ ইমেইল/টেলিগ্রাম যোগ করুন
4. ৪৮ ঘণ্টা পর দেখুন: চেক সবুজ, আর নিচের কমান্ডে ব্যাকআপ পাওয়া যায় —

```bash
python manage.py check_backups --max-age-hours 48 --check-remote
# প্রত্যাশিত: check_backups OK: newest backup backup-... (engine=postgres, ...)
```

---

## ৪. ধাপ ৪ — যাচাই চেকলিস্ট (একবার, লাইভে যাওয়ার আগে)

| # | কমান্ড / কাজ | প্রত্যাশিত ফল |
|---|---|---|
| ১ | `python manage.py production_preflight --no-color` | সমস্যা **০** (সতর্কতা থাকতে পারে) |
| ২ | `curl -s https://<ডোমেইন>/healthz/` | `{"status": "ok", "db": "ok"}` |
| ৩ | `python manage.py check --deploy` | কোনো `E012`/`E016` নেই |
| ৪ | লগইন → শিক্ষার্থী তালিকা → রেজাল্ট শীট | পেজ খোলে, স্টাইল ঠিক (manifest আছে) |
| ৫ | একজন শিক্ষার্থীর ছবি আপলোড | ছবি দেখা যায়, URL-এ signature |
| ৬ | `python manage.py check_backups --check-remote` | সবুজ |
| ৭ | Render → Postgres → Metrics | connection সংখ্যা স্বাভাবিক |
| ৮ | ২৪ ঘণ্টা পরে আবার ১ ও ৬ | তখনো সবুজ (cron সত্যিই চলছে) |

`production_preflight` যেগুলো দেখে (১০টি): DEBUG, SECRET_KEY, ALLOWED_HOSTS,
CSRF_TRUSTED_ORIGINS, DB ইঞ্জিন, `pg_dump`, মিডিয়া বাকেট, ব্যাকআপের বয়স,
static manifest, রেট-লিমিট কাউন্টার।

---

## ৫. মাসে একবার — রিস্টোর ড্রিল (২০ মিনিট)

> ব্যাকআপ "আছে" আর ব্যাকআপ "কাজ করে" এক জিনিস নয়। টেস্ট না করা ব্যাকআপ = আশা।

```bash
# ১) উৎপাদন DB-তে হাত দেবেন না — আলাদা ডেটাবেসে রিস্টোর করুন
#    (Render-এ একটা ছোট/ডেভ Postgres, অথবা নিজের ল্যাপটপে postgres)
export DATABASE_URL="postgres://...restore-target..."
python manage.py migrate

# ২) সর্বশেষ ব্যাকআপ রিস্টোর (বাকেট থেকে নামিয়ে নিন)
python manage.py restore_backup --backup /path/to/backup-20261105T203000Z \
    --yes --verify

# ৩) সংখ্যা মিলিয়ে দেখুন
python manage.py shell -c "
from students.models import Student, ExamMark
print('students', Student.objects.count(), '| marks', ExamMark.objects.count())"
```

উৎপাদনের সংখ্যার সাথে মিলে গেলে ব্যাকআপ বিশ্বাসযোগ্য। মিলল না — সেটাই সবচেয়ে
দামি তথ্য, সেটা নিয়েই তদন্ত শুরু করুন।

---

## ৬. খরচ (২০২৬, আনুমানিক)

| খাত | মাসিক | বার্ষিক (টাকা) |
|---|---|---|
| Render Web (Starter) | $৭ | ~৳১০,২০০ |
| Render Postgres Basic-256MB | $৬ | ~৳৮,৮০০ |
| Render Cron | $১ | ~৳১,৫০০ |
| Cloudflare R2 (ছবি, ১০ GB ফ্রি) | ~$০ | ~৳০ |
| ডোমেইন | — | ~৳১,২০০ |
| **মোট** | **~$১৪** | **~৳২১,৭০০** |

(১ USD ≈ ৳১২২ ধরা হয়েছে। Postgres-এর বড় প্ল্যান বা বেশি স্টোরেজ নিলে বার্ষিক
৳৩৫–৪৫ হাজার পর্যন্ত হতে পারে।) — এ কারণেই রক্ষণাবেক্ষণ ফি ৳৭৫,০০০-এর কম রাখা
মানে নিজের পকেট থেকে ভর্তুকি দেওয়া।

---

## ৭. সমস্যা ও সমাধান

| লক্ষণ | কারণ | সমাধান |
|---|---|---|
| সব পেজে 500, লগে `no such table` | migrate চলে নি / ভুল `DATABASE_URL` | `python manage.py migrate`; Render-এ `DATABASE_URL` যাচাই |
| 502 Bad Gateway | gunicorn ক্র্যাশ | Render → Logs → শেষ ৫০ লাইন; প্রায়ই env var ভুল বা `SECRET_KEY` নেই |
| স্টাইল/আইকন ভাঙা, 500 `Missing staticfiles manifest entry` | `collectstatic` চলে নি | Build command: `pip install -r requirements.txt && python manage.py collectstatic --noinput` |
| 400 DisallowedHost | `ALLOWED_HOSTS`-এ ডোমেইন নেই | ড্যাশবোর্ডে ডোমেইন যোগ করুন |
| লগইনে 403 CSRF | প্রক্সির পেছনে origin মিলছে না | `CSRF_TRUSTED_ORIGINS=https://ডোমেইন`, `TRUST_FORWARDED_PROTO=True` |
| ছবি 404 / ভাঙা | `USE_S3` বন্ধ বা কী ভুল | env var যাচাই; `check --deploy` চালান (E012) |
| `pg_dump: not installed` | runtime-এ ক্লায়েন্ট নেই | `deploy/backup-cron.Dockerfile` দিয়ে docker cron |
| `check_backups` ব্যর্থ: remote নেই | বাকেটে কপি হয়নি | `BACKUP_OBJECT_STORAGE_*` সব সেট; `--check-remote` মেসেজ পড়ুন |
| নতুন শিক্ষার্থী যোগে `duplicate key` | sequence reset করা হয়নি | `python manage.py reset_sequences` |
| "database is locked" | এখনো SQLite | `DATABASE_URL` Postgres-এ বদলান |
| লগআউট হয়ে যাচ্ছে বারবার | worker বদলাচ্ছে + locmem cache/session | `RATE_LIMIT_CACHE=db`; সেশন ডেটাবেসে (ডিফল্ট) থাকে |

---

## ৮. নিরাপত্তা — যা মনে রাখতেই হবে

- **`.env` বা আসল কী কখনো git-এ নয়।** লিক হলে: `SECRET_KEY` (সব সেশন বাতিল), ডেটাবেস পাসওয়ার্ড (Postgres → Rotate), R2 টোকেন (Revoke → নতুন)।
- **ব্যাকআপ পাসফ্রেজ আলাদা রাখুন** — ব্যাকআপ বাকেট আর পাসফ্রেজ একই জায়গায় থাকলে এনক্রিপশনের অর্থ থাকে না।
- **ছবির বাকেট প্রাইভেট** — শিক্ষার্থীর ছবি পাবলিক করা = নাবালকের ব্যক্তিগত তথ্য প্রকাশ।
- **সংখ্যার মালিকানা:** শিক্ষার্থীর ডেটা প্রতিষ্ঠানের, কোড আপনার — লিখিতভাবে স্পষ্ট রাখুন (`PRICING_CAREER_PLAN_BN.html` §৫)।
- বছরে একবার: চলে যাওয়া কর্মীর অ্যাকাউন্ট নিষ্ক্রিয়, পারমিশন রিভিউ, টোকেন রোটেশন।

---

## ৯. কে কী করবে

| কাজ | কে | সময় |
|---|---|---|
| কোড, কনফিগ, কমান্ড, টেস্ট, এই গাইড | ✅ আগেই করা হয়েছে (কমিটে) | — |
| Render অ্যাকাউন্ট, Postgres তৈরি, env var বসানো | আপনি (owner) | ১–২ ঘণ্টা |
| R2 বাকেট, টোকেন, ছবি যাচাই | আপনি | ৪৫ মিনিট |
| Cron + Healthchecks.io | আপনি | ৪৫ মিনিট |
| পুরোনো ডেটা সরানো + সংখ্যা মিলানো | আপনি (কমান্ড দেওয়া আছে) | ১–২ ঘণ্টা |
| রিস্টোর ড্রিল | আপনি | ২০ মিনিট |

---

## ১০. রোলব্যাক (যদি কিছু ভুল হয়)

1. Render → Environment → `DATABASE_URL` **আগের মানে** ফিরিয়ে দিন (অথবা নতুন সার্ভিসে পুরোনো SQLite/ব্যাকআপ)।
2. `USE_S3` বন্ধ করলেই ছবি আবার লোকাল ডিস্কে যাবে (তবে পুরোনো ছবি বাকেটে থাকবে — মিশে যাবে, তাই আগে ঠিক করুন)।
3. ডেটা সরানোর আগে নেওয়া ব্যাকআপ (`/tmp/pre-migration` বা বাকেট) — এটাই আপনার ফেরার পথ।
4. প্রতিটি ধাপের পরে `production_preflight` চালান — কোনটা এখনো বাকি, তা এক নজরে দেখাবে।

---

## সাথে সম্পর্কিত ফাইল

- `render.yaml` — web + Postgres + cron ব্লুপ্রিন্ট
- `deploy/backup-cron.Dockerfile` — pg_dump সহ cron ইমেজ
- `students/health.py` + `/healthz/` — হেলথ চেক (ডেটাবেস `SELECT 1`)
- `students/management/commands/production_preflight.py` — ১০ দফা যাচাই
- `students/management/commands/reset_sequences.py` — fixture লোডের পরে ID ফাঁদ
- `docs/BACKUP_AND_RESTORE.md`, `docs/BACKUP_RESTORE_GUIDE.md` — ব্যাকআপের বিস্তারিত
- `docs/FREE_TIER_MEDIA_STORAGE.md` — কেন `USE_S3` দরকার
- `docs/PRODUCTION_CHECKLIST.md` — লাইভ চেকলিস্ট
