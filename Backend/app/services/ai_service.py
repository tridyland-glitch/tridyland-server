import os
import json
import google.generativeai as genai
from dotenv import load_dotenv

load_dotenv()
genai.configure(api_key=os.getenv("GOOGLE_API_KEY"))

MODEL_NAME = "gemini-2.5-flash"

def generate_product_data(image_path: str, context: str, price: float = None, category_list: str = "") -> dict:
    print(f"   🧠 Consultando a Gemini ({MODEL_NAME})...")

    # --- CAMBIO IMPORTANTE: INSTRUCCIONES NEUTRALES ---
    system_instruction = """
    Eres un experto copywriter para 'Tridyland'. Tu tono es divertido, geek y persuasivo.
    
    CRITERIOS DE ANÁLISIS:
    1. NOMBRE DEL PRODUCTO (IMPORTANTE):
       - PRIORIZA el nombre exacto que el usuario da en el contexto (ej: "Cocofanto").
       - Puedes agregarle emojis o una palabra clave al final, pero NO cambies el nombre base.
       - Si el usuario dice "Cocofanto", no pongas "Elefante Coco-Fantástico".
    
    2. ANÁLISIS VISUAL:
       - Si ves/lees "clicker", "fidget", "mecánico": Vende ASMR.
       - Si no, asume FIGURA DECORATIVA / COLECCIONABLE.
    
    3. REGLAS JSON:
       - Título: El nombre del usuario + emoji. Max 70 chars.
       - Descripción: HTML básico.
       - Image Alt: Descripción visual detallada.
       - Tags: 10-15 etiquetas.
    """

    sample_file = genai.upload_file(path=image_path, display_name="Product Image")
    
    user_prompt = f"""
    Analiza esta imagen y el contexto.
    Contexto del usuario: "{context}"
    Precio sugerido: {price if price else "N/A"}
    
    CATEGORÍAS DISPONIBLES EN LA TIENDA (Solo usa IDs de esta lista):
    {category_list}
    
    Estructura JSON requerida:
    {{
        "name": "Título del producto",
        "description": "Descripción en HTML",
        "handle": "slug-url-amigable",
        "seo_title": "SEO Title",
        "seo_description": "Meta description",
        "tags": "tag1, tag2",
        "image_alt": "Descripción visual para ciegos/SEO", 
        "category_ids": [123], 
        "new_category_suggestion": "Nombre sugerido o null"
    }}
    """

    generation_config = genai.types.GenerationConfig(
        temperature=0.5, # Bajamos la temperatura para que invente menos
        response_mime_type="application/json" 
    )

    model = genai.GenerativeModel(model_name=MODEL_NAME, system_instruction=system_instruction)

    try:
        response = model.generate_content([user_prompt, sample_file], generation_config=generation_config)
        return json.loads(response.text)
    except Exception as e:
        print(f"❌ Error en Gemini: {e}")
        return {"error": str(e)}

def generate_social_media_pack(product_name: str, context: str, store_url: str) -> dict:
    """
    Genera un pack completo de contenido para YouTube, Instagram/TikTok y Facebook.
    """
    system_instruction = """
    Eres el Director de Marketing de 'Tridyland'. Tu personalidad es súper alegre, divertida y con toda la actitud regia (del norte de México). Eres un experto en cultura pop, anime, videojuegos y todo lo que sea friki/otaku.

    CRITERIOS DE TONO:
    - Actitud: Alegre, entusiasta y muy "pro". Nada de malas palabras.
    - Lenguaje: Usa términos como "está de lujo", "qué onda pariente", "clic adictivo", "joyita", "épico". 
    - Referencias: Integra cosas de cultura pop, cartoons y anime de forma natural.
    - Enfoque ASMR: Resalta la satisfacción sensorial, el sonido del clic y lo bien que se siente al tacto.
    - Sin tecnicismos: Cámbialos por descripciones que emocionen (ej. "acabado de otro planeta" en lugar de "capas de 0.2mm").

    ESTRUCTURA DE RESPUESTA (JSON):
    {
    "youtube_shorts": {
        "title": "Título con punch y emojis frikis",
        "description": "Copy divertido con link a www.tridyland.com y hashtags",
        "capcut_texts": ["Frases cortas para poner encima del video"]
    },
    "meta_reels": {
        "caption": "Texto aesthetic y alegre para FB/IG Reels",
        "on_screen_texts": ["Ganchos visuales para CapCut"],
        "story_ideas": ["Ideas para interactuar en Stories"]
    },
    "tiktok": {
        "caption": "Texto corto con mucha energía y hashtags virales",
        "capcut_hooks": ["Ganchos visuales que te hagan detener el scroll de volada"],
        "creative_idea": "Idea creativa: retos, comparaciones con anime, etc."
    },
    "ads_strategy": {
        "visual_hook": "Texto llamativo para el anuncio",
        "audio_script": "Guion alegre para que lo grabes tú (Gancho -> Qué hace especial al item -> ¡Llévatelo!)",
        "music_type": "Vibe musical alegre y sin copyright para publicidad",
        "cta_button": "Texto para el botón: ¡Lo quiero ya! 🚀"
    }
    }
    """

    user_prompt = f"""
    Producto: {product_name}
    Detalles: {context}
    Enlace de compra: {store_url}
    
    Genera el pack completo en JSON. Asegúrate de que los títulos de YouTube sean MUY llamativos.
    """

    model = genai.GenerativeModel(model_name=MODEL_NAME, system_instruction=system_instruction)
    
    try:
        response = model.generate_content(user_prompt, generation_config={"response_mime_type": "application/json"})
        return json.loads(response.text)
    except Exception as e:
        return {"error": str(e)}