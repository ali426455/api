# Dockerfile for EUR/USD Trading Bot
# اپلیکیشن Streamlit برای روی Koyeb

FROM python:3.11-slim

# تنظیم متغیرهای محیطی
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1

# نصب وابستگی‌های سیستمی
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# تنظیم دایرکتوری کاری
WORKDIR /app

# کپی فایل وابستگی‌ها
COPY requirements.txt .

# نصب وابستگی‌های Python
RUN pip install --no-cache-dir -r requirements.txt

# کپی کد اپلیکیشن
COPY . .

# باز کردن پورت
EXPOSE 8501

# اجرای اپلیکیشن
CMD ["streamlit", "run", "app.py", "--server.port=8501", "--server.address=0.0.0.0", "--server.headless=true"]
