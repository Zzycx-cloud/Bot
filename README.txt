UNIPRO BOT - DATABASELI TAYYOR PAKET

1) NIMA TO'GRILANDI
- Xotiradagi dict/set lar orniga SQLite database qilindi
- users, orders, referrals, admin_logs, pending_actions jadvallari qoshildi
- restart bolganda malumotlar saqlanib qoladi
- token kod ichidan olindi, .env ga kochirildi

2) DATABASE QAYERDAN OLASAN?
- Hech qayerdan olmaysan.
- Botni ishga tushirsang, shu papkaning ichida bot.db degan fayl ozi yaratiladi.
- Bu SQLite database.

3) TOKENNI ALMASHTIR
- Eski token kodingda ochiq qolgan. BotFather dan yangi token ol.
- Yangi tokenni .env faylga yoz.

4) QANDAY ISHGA TUSHIRASAN
Windows CMD / Terminal:

pip install -r requirements.txt
copy .env.example .env

Keyin .env ichini ochib oz qiymatlaringni yoz:
- BOT_TOKEN
- ADMIN_REVIEW_CHAT_ID
- OWNER_ID

So'ng:
python main.py

5) DATABASENI KO'RISH
- bot.db fayl paydo bo'ladi
- Uni DB Browser for SQLite bilan ochib ko'rsa bo'ladi

6) MUHIM ESLATMA
- Agar admin review chat id noto'gri bo'lsa, order yuborishda xato bo'ladi
- Botni private ochib /start bosing, user users jadvaliga yoziladi
