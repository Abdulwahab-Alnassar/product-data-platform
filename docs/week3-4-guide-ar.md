# الأسبوع الثالث والرابع — النسخة الأساسية للمشروع

هذه المرحلة تكمل مشروع هندسة البيانات للشهر الأول، وليست نهاية خطة التعلم ذات الستة أشهر.
المشروع لا يتضمن حتى الآن تعلم آلة أو RAG أو بيانات لحظية، ولا يعتبر خدمة إنتاج عامة.

## الأسبوع الثالث: PostgreSQL وDocker

1. اقرأ `src/postgres_storage.py`: الاتصال يأتي من متغيرات البيئة أو `.env`، ولا نضع كلمة المرور في الكود.
2. اقرأ `sql/postgres/schema.sql`: نفس حقول SQLite، لكن الأسعار NUMERIC وأعداد التقييمات BIGINT.
3. تابع `load_database`: نتحقق من الأعمدة والهوية، ثم نحفظ الدفعة داخل transaction واحدة.
4. افهم upsert: المنتج الجديد يضاف، والموجود يتحدث. NULL القادم يستبدل القيمة القديمة، والمنتج الغائب عن الدفعة لا يحذف.
5. جدول مؤقت يقارن القيم المخزنة بالدفعة قبل commit؛ أي فشل يرجع تغييرات الدفعة. ملفات CSV وتقارير الجودة ليست جزءًا من معاملة قاعدة البيانات.
6. اقرأ `Dockerfile` ثم `compose.yaml`: قاعدة البيانات تستعد أولًا، ثم pipeline يحمّل العينة، ثم الواجهة تبدأ. البيانات تبقى في volume عند إيقاف الحاويات.
7. اقرأ `tests/test_postgres.py`: اختبارات حقيقية على PostgreSQL مع schema مؤقت لكل اختبار. لا تشغّلها على قاعدة إنتاج.

## الأسبوع الرابع: واجهة العرض والتسليم

1. اقرأ `src/query_data.py`: SQLite يفتح بوضع القراءة فقط؛ PostgreSQL يستخدم معاملة قراءة فقط.
2. اقرأ `dashboard.py`: تحميل البيانات ثم فلاتر الاسم/المعرف والتصنيف والتقييم.
3. المؤشرات تصف المنتجات الموجودة بعد الفلترة، وليست مبيعات أو إيرادات. الأسعار INR وليست ريالًا سعوديًا.
4. القيم الناقصة ليست أصفارًا. خيار Include unrated products يتحكم بعرض المنتجات دون تقييم.
5. التصدير يضيف علامة اقتباس قبل النصوص التي قد تفسرها برامج الجداول كصيغ. لا يتم تصدير كلمات مرور.
6. اقرأ `tests/test_dashboard.py`: تشغيل الواجهة آليًا وفحص الفلاتر وحالة قاعدة البيانات المفقودة.
7. افتح Actions على GitHub: فحوص Windows وLinux، PostgreSQL، وتشغيل Docker الكامل.

## تشغيل سريع بدون Docker — PowerShell

من مجلد المشروع وبعد تفعيل البيئة الافتراضية:

```powershell
git pull --ff-only origin main
python -m pip install -r requirements.txt
python -m pytest -v
python -m src.pipeline --input data/sample/amazon_sample.csv --output-dir data/processed/demo
$env:SQLITE_PATH = 'data/processed/demo/products.db'
python -m streamlit run dashboard.py
```

افتح http://localhost:8501. أوقف الواجهة باستخدام Ctrl+C.
اختبارات PostgreSQL تظهر skipped ما لم تضبط TEST_DATABASE_URL؛ هذا متوقع محليًا.
لتشغيل بياناتك الكاملة استخدم `python -m src.pipeline` ثم اجعل SQLITE_PATH يشير إلى `data/processed/products.db`.

## تشغيل PostgreSQL مع Docker Desktop

شغّل Docker Desktop بوضع Linux containers أولًا. في PowerShell:

```powershell
Copy-Item .env.example .env
```

افتح `.env` وضع كلمة مرور قوية غير فارغة في POSTGRES_PASSWORD. لا ترفع الملف ولا ترسل كلمة المرور في المحادثة.
لا تستبدل `.env` إذا كان موجودًا ويحتوي إعداداتك؛ عدّل القيم اللازمة فقط.

```powershell
docker compose up --build -d --wait dashboard
docker compose ps -a
```

افتح http://localhost:8501. أول تشغيل يستخدم العينة المضمنة صراحة، ولا يستخدم ملفك المحلي الكامل تلقائيًا.
خروج حاوية pipeline بالحالة Exited (0) طبيعي لأنها مهمة تنتهي بعد التحميل.
لعرض التقرير والسجل:

```powershell
docker compose logs pipeline
docker compose run --rm pipeline
```

الأمر الأخير يعيد تحميل العينة ويحدّث المنتجات نفسها بدون تكرارها. اضغط Refresh data في الواجهة.
لا تنشر الواجهة على الإنترنت: لا يوجد تسجيل دخول، وحساب PostgreSQL الحالي للتجربة وليس حساب قراءة منفصلًا.
منفذ الواجهة مربوط بـ127.0.0.1؛ قاعدة PostgreSQL غير مكشوفة على الجهاز المضيف.

### تحميل ملفك الكامل داخل Docker

```powershell
docker compose run --rm -v "${PWD}/data/raw:/input:ro" pipeline python -m src.pipeline --backend postgres --input /input/amazon.csv --output-dir data/processed
```

يلزم وجود `data/raw/amazon.csv`. تأكد أنك تسمح بمعالجة محتوى الملف؛ إزالة user_id وuser_name لا تعني إخفاء كل المعلومات الشخصية في نصوص المراجعات.

### إيقاف ونسخة احتياطية

```powershell
docker compose exec db pg_dump -U products_app -d products -Fc -f /tmp/products.backup
docker compose cp db:/tmp/products.backup ./products.backup
docker compose down
```

إذا غيّرت المستخدم أو اسم القاعدة، عدلهما في أمر النسخ. ملف النسخة الاحتياطية محلي ومتجاهل في Git.
`down` يبقي البيانات. لا تضف `-v` لأنه يحذف volumes وبياناتها.
لتجربة الاستعادة استخدم قاعدة جديدة فارغة، وليس قاعدة عملك، ثم `pg_restore` بالنسخة الاحتياطية.
تغيير POSTGRES_PASSWORD في `.env` لا يغير كلمة مرور قاعدة موجودة في volume؛ احتفظ بإعداداتك الأصلية أو غيّر كلمة المرور داخل PostgreSQL عمدًا.

## كيف تعرف أنك أنهيت النسخة الأساسية؟

- اختبارات GitHub خضراء، وpipeline ينتهي بنجاح على جهازك.
- تستطيع البحث والفلترة وتنزيل CSV من الواجهة.
- تفهم الفرق بين cleaned_rows وbatch_rows وdatabase_rows.
- تستطيع شرح لماذا المعاملة تتراجع عند الفشل، ولماذا CSV ليس داخل نفس المعاملة.
- تستطيع تشغيل العرض مرة ثانية دون مضاعفة المنتجات.

## حدود النسخة الحالية

لا توجد مصادقة أو صلاحيات متعددة أو جدولة إنتاجية أو migrations لتغييرات schema المستقبلية.
الواجهة تحمل بيانات العرض في الذاكرة، وهي مناسبة لهذه العينة لا لملايين السجلات.
تقرير الجودة يخص آخر دفعة وصلت لمرحلة الفحص وليس كل القاعدة؛ فشل مبكر قد يترك تقريرًا قديمًا، لذلك راجع سجل التشغيل الحالي.
لا تدعم تشغيل دفعتين بالتزامن على مجلد المخرجات نفسه.
قبل استخدام إنتاجي يلزم فصل مستخدم القراءة، إدارة أسرار ونسخ احتياطية مختبرة، ترحيل schema، مراقبة، وتثبيت كامل لإصدارات التبعيات.

## وصف مختصر صادق للمشروع

بنيت منصة دفعات لمعالجة بيانات منتجات باستخدام Python وPandas، مع فحوص جودة وعمليات upsert معاملية في SQLite وPostgreSQL، وتحليلات SQL ولوحة Streamlit، وتشغيل Docker واختبارات GitHub Actions.
