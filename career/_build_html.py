#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""career/*.md -> index.html (hub) + সব-একসাথে.html (everything inline)."""
import os, re, glob, html

HERE = os.path.dirname(os.path.abspath(__file__))

INLINE = re.compile(r'(\*\*.+?\*\*|`[^`]+`)')


def inline_md(t):
    t = html.escape(t, quote=False)
    parts = INLINE.split(t)
    out = []
    for p in parts:
        if not p:
            continue
        if p.startswith('**') and p.endswith('**') and len(p) > 4:
            out.append('<strong>%s</strong>' % p[2:-2])
        elif p.startswith('`') and p.endswith('`') and len(p) > 2:
            out.append('<code>%s</code>' % p[1:-1])
        else:
            out.append(p)
    return ''.join(out)


def esc_cell(t):
    return inline_md(t.strip())


def md_to_html(md_text):
    lines = md_text.split('\n')
    out = []
    i, n = 0, len(lines)
    while i < n:
        line = lines[i]
        s = line.strip()

        if s.startswith('```'):
            i += 1
            buf = []
            while i < n and not lines[i].strip().startswith('```'):
                buf.append(lines[i])
                i += 1
            i += 1
            out.append('<pre>' + html.escape('\n'.join(buf)) + '</pre>')
            continue

        if s.startswith('|') and s.endswith('|') and i + 1 < n and re.fullmatch(r'\|[\s:\-|]+\|', lines[i + 1].strip()):
            head = [c.strip() for c in s.strip('|').split('|')]
            i += 2
            rows = []
            while i < n and lines[i].strip().startswith('|') and lines[i].strip().endswith('|'):
                rows.append([c.strip() for c in lines[i].strip().strip('|').split('|')])
                i += 1
            out.append('<table><thead><tr>' + ''.join('<th>%s</th>' % esc_cell(h) for h in head) + '</tr></thead><tbody>')
            for r in rows:
                out.append('<tr>' + ''.join('<td>%s</td>' % esc_cell(r[k] if k < len(r) else '') for k in range(len(head))) + '</tr>')
            out.append('</tbody></table>')
            continue

        if s.startswith('# '):
            out.append('<h1>%s</h1>' % inline_md(s[2:])); i += 1; continue
        if s.startswith('## '):
            out.append('<h2>%s</h2>' % inline_md(s[3:])); i += 1; continue
        if s.startswith('### '):
            out.append('<h3>%s</h3>' % inline_md(s[4:])); i += 1; continue
        if re.fullmatch(r'-{3,}', s):
            out.append('<hr>'); i += 1; continue
        if s.startswith('> '):
            out.append('<blockquote>%s</blockquote>' % inline_md(s[2:])); i += 1; continue

        m = re.match(r'^(\s*)([-*])\s+(.*)$', line)
        if m:
            items = []
            while i < n:
                m2 = re.match(r'^(\s*)([-*])\s+(.*)$', lines[i])
                if not m2:
                    break
                items.append(inline_md(m2.group(3)))
                i += 1
            out.append('<ul>' + ''.join('<li>%s</li>' % it for it in items) + '</ul>')
            continue

        m = re.match(r'^(\s*)(\d+\.)\s+(.*)$', line)
        if m:
            items = []
            while i < n:
                m2 = re.match(r'^(\s*)(\d+\.)\s+(.*)$', lines[i])
                if not m2:
                    break
                items.append(inline_md(m2.group(3)))
                i += 1
            out.append('<ol>' + ''.join('<li>%s</li>' % it for it in items) + '</ol>')
            continue

        if not s:
            i += 1
            continue

        para = [inline_md(s)]
        i += 1
        while i < n and lines[i].strip() and not re.match(r'^(#{1,3} |> |\|{1}|\s*[-*]\s|\s*\d+\.\s|```)', lines[i]) and not re.fullmatch(r'-{3,}', lines[i].strip()):
            para.append(inline_md(lines[i].strip()))
            i += 1
        out.append('<p>' + '<br>'.join(para) + '</p>')

    return '\n'.join(out)


CSS = """
:root{--ink:#16233b;--muted:#5b6b85;}
*{box-sizing:border-box}
body{margin:0;font-family:"Nirmala UI","Vrinda","SolaimanLipi",Kalpurush,system-ui,-apple-system,"Segoe UI",sans-serif;
 background:#f4f6fb;color:#16233b;line-height:1.75;font-size:16px}
.wrap{max-width:900px;margin:0 auto;padding:28px 20px 80px}
h1{font-size:26px;line-height:1.4;margin:0 0 6px}
h2{font-size:20px;margin:30px 0 8px;padding-bottom:6px;border-bottom:2px solid #dfe6f2}
h3{font-size:17px;margin:22px 0 6px}
p,li{font-size:16px}
code{background:#eef1f8;padding:1px 5px;border-radius:4px;font-size:14px}
pre{background:#0f1a2e;color:#e7edf9;padding:14px 16px;border-radius:10px;overflow-x:auto;font-size:13.5px;line-height:1.6}
blockquote{margin:12px 0;padding:10px 14px;background:#fff7e6;border-left:4px solid #f0b429;border-radius:0 8px 8px 0}
table{width:100%;border-collapse:collapse;margin:14px 0;font-size:14.5px;background:#fff}
th,td{border:1px solid #dfe6f2;padding:8px 10px;text-align:left;vertical-align:top}
th{background:#eaf0fb;font-weight:700}
hr{border:0;border-top:1px solid #dfe6f2;margin:24px 0}
.hero{background:linear-gradient(135deg,#0f5132,#198754);color:#fff;border-radius:14px;padding:22px 24px;margin-bottom:22px}
.hero h1{color:#fff;margin-bottom:6px}
.hero p{color:#d9f2e4;margin:0}
.hero a{color:#fff;font-weight:700}
.card{background:#fff;border:1px solid #e3e9f4;border-radius:12px;padding:16px 18px;margin:12px 0;box-shadow:0 1px 2px rgba(16,35,59,.05)}
.card h3{margin:0 0 4px}
.card p{margin:4px 0;color:#46536b}
a{color:#0d6efd}
.badge{display:inline-block;background:#eaf0fb;color:#2b4a80;border-radius:20px;padding:2px 10px;font-size:12px;margin-left:8px}
ol.big>li{margin:8px 0}
.doc-nav{position:sticky;top:0;background:rgba(244,246,251,.95);backdrop-filter:blur(6px);padding:10px 0;border-bottom:1px solid #e3e9f4;margin-bottom:18px}
.doc-nav a{margin-right:12px;font-size:14px}
footer{margin-top:40px;color:#6b7891;font-size:13px}
"""

DOC_META = {
    '00': ('শুরু করার আগে', '৩০ সেকেন্ডের ওরিয়েন্টেশন — কোন ফাইল কখন পড়বেন, তিনটি লাল রেখা'),
    '01': ('বাস্তবতা', 'গতবার কেন হেরে গেলেন, প্রমোশনের চারটি মুদ্রা, রাজনীতির মানচিত্র'),
    '02': ('নিরাপত্তার ১২ নিয়ম', 'কী বলবেন / কী বলবেন না, টাকার বিষয়ে লাল রেখা, প্রকৃত প্রস্তুতি'),
    '03': ('নব্বই দিনের পরিকল্পনা', 'দিন ১–৩০ / ৩১–৬০ / ৬১–৯০ — কী করবেন, কার লাভ, কী প্রমাণ জমবে'),
    '04': ('প্রপোজাল খসড়া', 'কপি-পেস্ট করে জমা দেবেন — ৩টি চিঠি + ব্যক্তিগত বৈঠকের স্ক্রিপ্ট'),
    '05': ('প্রমাণ-রেকর্ড ও ACR', 'প্রমাণ-খাতার কলাম, মাসিক এক পাতা, আত্ম-মূল্যায়নের নমুনা'),
    '06': ('বাইরের বাজার', 'BATNA, ৩০ দিনে বাইরের দরজা খোলার কাজ, সতর্কতা'),
    '07': ('স্ক্রিপ্ট ও লাল পতাকা', 'পরিস্থিতি অনুযায়ী আক্ষরিক বাক্য + ৭টি লাল পতাকা + আগামীকালের কাজ'),
}


def main():
    files = sorted(glob.glob(os.path.join(HERE, '*.md')))
    files = [f for f in files if not os.path.basename(f).startswith('_')]

    # ---------- combined ----------
    body = []
    nav = []
    for f in files:
        base = os.path.basename(f)
        key = base[:2]
        title, desc = DOC_META.get(key, (base, ''))
        slug = re.sub(r'[^0-9a-zA-Z]+', '-', key)
        nav.append('<a href="#doc-%s">%s</a>' % (slug, key))
        with open(f, encoding='utf-8') as fh:
            content = md_to_html(fh.read())
        body.append('<section id="doc-%s" class="card">%s</section>' % (slug, content))
    combined = """<!doctype html><html lang="bn"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>ক্যারিয়ার পরিকল্পনা — সব একসাথে</title><style>%s</style></head><body><div class="wrap">
<div class="hero"><h1>ক্যারিয়ার পরিকল্পনা — সব একসাথে</h1>
<p>প্রমোশন আদায়ের ৯০ দিনের খসড়া · ১৮ সেপ্টেম্বর ২০২৬ · <a href="index.html">← হাবে ফিরুন</a></p></div>
<div class="doc-nav">%s</div>
%s
<footer>এই নথিগুলো আপনার <code>school-management-system</code> রিপোজিটরির <code>career/</code> ফোল্ডারে আছে — বাংলায়, ছাপার জন্য <code>word/</code> ফোল্ডারে Word ফাইল।</footer>
</div></body></html>""" % (CSS, ''.join(nav), '\n'.join(body))
    with open(os.path.join(HERE, 'সব-একসাথে.html'), 'w', encoding='utf-8') as fh:
        fh.write(combined)
    print('OK সব-একসাথে.html')

    # ---------- index ----------
    cards = []
    for f in files:
        base = os.path.basename(f)
        key = base[:2]
        title, desc = DOC_META.get(key, (base, ''))
        docx = 'word/' + os.path.splitext(base)[0] + '.docx'
        slug = re.sub(r'[^0-9a-zA-Z]+', '-', key)
        cards.append(
            '<div class="card"><h3>%s · %s <span class="badge">%s</span></h3>'
            '<p>%s</p>'
            '<p><a href="সব-একসাথে.html#doc-%s">ব্রাউজারে পড়ুন</a> · '
            '<a href="%s">Word (.docx)</a> · <a href="%s">Markdown</a></p></div>'
            % (key, html.escape(title), key, html.escape(desc), slug,
               html.escape(docx), html.escape(base)))

    index = """<!doctype html><html lang="bn"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>ক্যারিয়ার ডকুমেন্ট হাব</title><style>%s</style></head><body><div class="wrap">
<div class="hero"><h1>ক্যারিয়ার ডকুমেন্ট হাব</h1>
<p>প্রমোশন কীভাবে আদায় করবেন — ৮টি নথি। <a href="career-package.zip">⬇ সব একসাথে (.zip)</a> ·
<a href="সব-একসাথে.html">📖 ১২ মিনিটে সব পড়ুন</a></p></div>

<div class="card" style="border-left:5px solid #198754">
<h3>আগে এই তিনটি লাইন</h3>
<ol class="big">
<li><strong>সফটওয়্যার দিয়ে প্রমোশন হয় না</strong> — উপরের কৃতিত্ব, জোট, প্রমাণ আর বিকল্প দিয়ে হয়। সফটওয়্যার সেই চারটির ইন্ধন।</li>
<li><strong>গতবার আপনি হেরেছেন কারণ</strong> "ওদের সফটওয়্যারে দুর্বলতা আছে" — কর্তার কানে শোনায় "আপনার সিদ্ধান্ত ভুল"। এবার কাউকে না ছুঁয়ে শুধু কাজ যোগ করবেন।</li>
<li><strong>আসল লিভারেজ ভেতরে নয়, বাইরে</strong> — যার বিকল্প থাকে, তারই দাম বাড়ে। বাইরের দরজা ৩০ দিনের মধ্যে খুলুন (<a href="সব-একসাথে.html#doc-06">০৬</a>)।</li>
</ol></div>

<h2>নথিগুলো</h2>
%s

<h2>আজই যা করবেন (১০ মিনিট)</h2>
<div class="card"><ol class="big">
<li>প্রমাণ-খাতা খুলুন — আজকের তারিখে প্রথম লাইন (<a href="সব-একসাথে.html#doc-05">০৫</a>)</li>
<li>দুজনকে জিজ্ঞেস করুন: "আপনার সবচেয়ে বিরক্তিকর কাজটা কোনটি?" — উত্তর লিখুন</li>
<li><a href="সব-একসাথে.html#doc-04">০৪</a> নম্বরের খসড়া ১ নাম-পদ বসিয়ে <strong>আজই</strong> জমা দিন</li>
<li>সন্ধ্যায়: GitHub প্রোফাইল + CV (<a href="সব-একসাথে.html#doc-06">০৬</a>)</li>
</ol></div>

<footer>রিপোজিটরি: <code>school-management-system/career/</code> · তৈরি: ১৮ সেপ্টেম্বর ২০২৬</footer>
</div></body></html>""" % (CSS, '\n'.join(cards))
    with open(os.path.join(HERE, 'index.html'), 'w', encoding='utf-8') as fh:
        fh.write(index)
    print('OK index.html')


if __name__ == '__main__':
    main()
