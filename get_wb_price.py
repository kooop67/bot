import requests

def get_wb_product(article: str) -> dict:
    try:
        url = f"https://card.wb.ru/cards/v1/detail?appType=1&curr=rub&dest=-1257786&spp=0&nm={article}"
        response = requests.get(url, timeout=10)
        response.raise_for_status()

        data = response.json()
        product = data.get("data", {}).get("products", [])[0]

        if product.get("totalQuantity", 0) == 0:
            return {"error": "❗ Товара нет в наличии."}

        price_u = product.get("priceU")
        sale_price_u = product.get("salePriceU")

        if sale_price_u:
            price_value = sale_price_u / 100  # числовая цена со скидкой
            price_str = f"{int(price_value)} ₽ (со скидкой)"
        elif price_u:
            price_value = price_u / 100
            price_str = f"{int(price_value)} ₽"
        else:
            price_value = None
            price_str = "❗ Цена недоступна."

        name = product.get("name", "Название не найдено")

        pic_id = product.get("id")
        img_url = None
        if pic_id:
            img_url = f"https://images.wbstatic.net/c516x688/{pic_id}-1.jpg"

        return {
            "name": name,
            "price_str": price_str,  # для показа пользователю
            "price_value": price_value,  # для хранения в базе
            "img_url": img_url
        }

    except IndexError:
        return {"error": "❗ Товар не найден. Проверь артикул."}
    except Exception as e:
        print(f"[ERROR] Парсинг JSON API Wildberries: {e}")
        return {"error": "⚠️ Ошибка при получении данных."}
