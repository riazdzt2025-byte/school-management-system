# দৈনিক ব্যাকআপ cron-এর জন্য ছোট ইমেজ — PostgreSQL ক্লায়েন্ট সহ।
#
# কেন দরকার: Render-এর Python runtime-এ `pg_dump` নাও থাকতে পারে, আর
# Postgres ব্যাকআপ `pg_dump` ছাড়া হয় না। এই ইমেজে postgresql-client আগেই
# বসানো, তাই `manage.py backup_data` নির্ভরযোগ্যভাবে চলবে।
#
# ব্যবহার (render.yaml-এ cron সার্ভিসের জন্য):
#   runtime: docker
#   dockerfilePath: ./deploy/backup-cron.Dockerfile
#   dockerContext: .
#
# স্থানীয়ভাবে পরীক্ষা:
#   docker build -f deploy/backup-cron.Dockerfile -t sms-backup .
#   docker run --rm -e DATABASE_URL="postgres://..." -e P0B_BACKUP_ROOT=/tmp/b \
#       -e HEALTHCHECK_PING_URL="" sms-backup

FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

# pg_dump/pg_restore (একই মেজর ভার্সন), curl (Healthchecks.io ping),
# gpg + openssl (ব্যাকআপ এনক্রিপশন), tar (media আর্কাইভ)
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        postgresql-client \
        curl \
        ca-certificates \
        gnupg \
        openssl \
        tar \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt ./
RUN pip install -r requirements.txt

COPY . .
RUN chmod +x scripts/*.sh

# cron সার্ভিস একবার চলে ও শেষ হয় — তাই CMD, এবং `backup_cron.sh` ব্যর্থ হলে
# নন-জিরো exit দেয় (Render + Healthchecks.io দুটোই টের পায়)।
CMD ["./scripts/backup_cron.sh"]
