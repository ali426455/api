# 🚀 راهنمای استقرار روی Koyeb

## مراحل اجرای ربات روی Koyeb (رایگان و ۲۴/۷)

### پیش‌نیازها:
1. یک حساب GitHub (رایگان)
2. یک حساب Koyeb (رایگان - بدون کارت اعتباری)

---

## مرحله ۱: آپلود کد روی GitHub

کد همین الان روی ریپوی زیر قرار دارد — لازم نیست خودتان `git init` بزنید:

**ریپو:** [https://github.com/ali426455/api](https://github.com/ali426455/api)

اگر بعداً تغییری دادید، فقط این‌ها کافی است:

```bash
git add .
git commit -m "Update trading bot"
git push
```

---

## مرحله ۲: ساخت حساب Koyeb

1. به [koyeb.com](https://www.koyeb.com) بروید
2. روی **Sign Up** کلیک کنید
3. با GitHub ثبت‌نام کنید (ساده‌ترین روش)
4. **هیچ کارت اعتباری لازم نیست!**

---

## مرحله ۳: ساخت سرویس جدید

1. در داشبورد Koyeb، روی **Create App** کلیک کنید
2. مراحل زیر را دنبال کنید:

### Step 1: Deployment Source
- **Deployment method:** GitHub
- **Repository:** `YOUR_USERNAME/forex-trading-bot`
- **Branch:** `main`
- **Build method:** Docker

### Step 2: App configuration
- **Name:** `eurusd-trading-bot`
- **Region:** Frankfurt (یا نزدیک‌ترین منطقه)

### Step 3: Instance configuration
- **Instance type:** Nano (رایگان - 0.1 CPU, 512MB RAM)

### Step 4: Environment variables
- نیازی نیست (همه چیز در کد تنظیم شده)

### Step 5: Ports
- **Port:** `8501`
- **Protocol:** HTTP

### Step 6: Health checks
- **Type:** HTTP
- **Path:** `/`
- **Port:** `8501`

---

## مرحله ۴: Deploy!

روی **Create App** کلیک کنید و صبر کنید تا:
1. Docker Image ساخته شود (۲-۵ دقیقه)
2. سرویس روشن شود
3. لینک دسترسی داده شود

🎉 **تمام!** ربات شما الان روی اینترنت در دسترس است و ۲۴/۷ فعال است.

---

## لینک دسترسی

بعد از Deploy، Koyeb یک لینک مثل این می‌دهد:
```
https://eurusd-trading-bot-username.koyeb.app
```

این لینک را در مرورگر باز کنید و ربات کار می‌کند!

---

## به‌روزرسانی خودکار

هر بار که تغییراتی در کد دهید و push کنید:
```bash
git add .
git commit "Updated strategy"
git push
```

Koyeb خودکار سرویس را به‌روزرسانی می‌کند!

---

## محدودیت‌های پلن رایگان Koyeb

| ویژگی | مقدار |
|-------|-------|
| سرویس | ۱ سرویس رایگان |
| CPU | 0.1 vCPU |
| RAM | 512 MB |
| Storage | 2 GB SSD |
| Uptime | ۲۴/۷ (همیشه روشن) |
| دامنه سفارشی | ✅ پشتیبانی می‌شود |
| SSL | ✅ رایگان |

---

## عیب‌یابی

### سرویس روشن نمی‌شود:
1. لاگ‌ها را در Koyeb چک کنید
2. مطمئن شوید `requirements.txt` درست است
3. پورت 8501 را چک کنید

### خطای Memory:
- اگر RAM کافی نیست، پوریود داده را کمتر کنید (مثلاً `1mo` به `5d`)

### کندی سایت:
- پلن رایگان Koyeb برای استفاده معمولی کافی است
- برای سرعت بیشتر، پلن پولی ($5/ماه) را در نظر بگیرید

---

## گزینه‌های جایگزین

اگر Koyeb کار نکرد:

1. **Render** - [render.com](https://render.com)
   - مشابه Koyeb، رایگان با محدودیت
   
2. **Google Cloud Run** - 2M درخواست/ماه رایگان
   - نیاز به دانش Docker بیشتر

3. **PythonAnywhere** - برای اجرای اسکریپت‌ها
   - محدودیت اجرای روزانه
