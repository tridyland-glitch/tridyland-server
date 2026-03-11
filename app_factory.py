import streamlit as st
import requests
import json

# --- CONFIGURACIÓN ---
BASE_URL = "https://api.tridyland.com/api/v1/tiendanube"
st.set_page_config(page_title="Tridyland Factory Hub", page_icon="🏭", layout="wide")

# --- ESTILOS CUSTOM ---
st.markdown("""
    <style>
    .main {
        background-color: #f5f7f9;
    }
    .stButton>button {
        border-radius: 10px;
        height: 3em;
    }
    </style>
    """, unsafe_allow_html=True)

# --- UI PRINCIPAL ---
st.title("🏭 Tridyland Factory Hub")
st.markdown("Sistema Centralizado de Automatización 3D")

# Creamos las pestañas
tab_factory, tab_marketing = st.tabs(["🏗️ Producción de Catálogo", "📱 Marketing Viral (Shorts)"])

# --- PESTAÑA 1: FÁBRICA ---
with tab_factory:
    st.header("Crear Nuevo Producto")
    st.info("Sube las fotos crudas y la IA se encargará del resto: crop, SEO y subida.")
    
    col_text, col_price = st.columns([2, 1])
    with col_text:
        context = st.text_input("📝 Contexto del producto", placeholder="Ej: Cocofanto elefante brainrot, acabado mate...")
    with col_price:
        price = st.number_input("💰 Precio MXN", min_value=0, value=179, step=10)

    st.markdown("---")
    c1, c2 = st.columns(2)
    with c1:
        main_image = st.file_uploader("⭐ FOTO PRINCIPAL", type=['png', 'jpg', 'jpeg'])
    with c2:
        gallery_images = st.file_uploader("🖼️ GALERÍA", type=['png', 'jpg', 'jpeg'], accept_multiple_files=True)

    if st.button("🚀 FABRICAR Y SUBIR A TIENDANUBE", type="primary", use_container_width=True):
        if not context or not main_image:
            st.error("⚠️ El contexto y la foto principal son obligatorios.")
        else:
            with st.spinner("⚙️ Procesando imágenes y consultando a Gemini..."):
                try:
                    files = [('main_image', (main_image.name, main_image.getvalue(), main_image.type))]
                    if gallery_images:
                        for img in gallery_images:
                            files.append(('gallery_images', (img.name, img.getvalue(), img.type)))

                    data = {"context": context, "price_guess": price}
                    
                    response = requests.post(f"{BASE_URL}/process-draft", data=data, files=files)
                    
                    if response.status_code in [200, 201]:
                        res = response.json()
                        tn = res.get("tiendanube_result", {})
                        ai = res.get("ai_summary", {})
                        
                        st.success(f"✅ ¡Producto Fabricado! SKU: {ai.get('sku')}")
                        st.balloons()
                        
                        if "admin_url" in tn:
                            st.link_button("🔗 EDITAR EN TIENDANUBE", tn['admin_url'])
                        
                        with st.expander("📦 Ver detalles del borrador"):
                            st.json(ai)
                    else:
                        st.error(f"❌ Error: {response.text}")
                except Exception as e:
                    st.error(f"❌ Fallo de conexión: {e}")

# --- PESTAÑA 2: MARKETING ---
with tab_marketing:
    st.header("🚀 Tridyland Marketing Hub")
    st.write("Genera estrategias específicas y guiones con toda la actitud regia.")
    
    product_url = st.text_input("🔗 URL del Producto", placeholder="https://tridyland.com/productos/...", key="mkt_url")
    
    platform = st.selectbox("📱 ¿Dónde vamos a publicar hoy?", 
                        ["YouTube Shorts", "TikTok", "Meta (FB/IG) Reels", "Guion de Anuncio (Ads)"])
    
    if st.button("✨ GENERAR ESTRATEGIA VIRAL", type="primary", use_container_width=True):
        if not product_url:
            st.warning("⚠️ Pega una URL válida.")
        else:
            with st.spinner("🧠 Gemini está craneando la campaña..."):
                try:
                    res = requests.post(f"https://api.tridyland.com/api/v1/tiendanube/social-pack-by-url", json={"url": product_url})
                    if res.status_code == 200:
                        data = res.json()
                        pack = data['social_pack']
                        
                        st.divider()
                        col_info, col_img = st.columns([2, 1])
                        with col_img:
                            if data.get('main_image'):
                                st.image(data['main_image'], caption=data['product'], use_container_width=True)
                        with col_info:
                            st.subheader(f"Campaña: {data['product']}")
                            st.success("¡Estrategia generada al puro estilo Tridyland! 🎉")

                        # --- LÓGICA POR PLATAFORMA ---
                        
                        if platform == "YouTube Shorts":
                            yt = pack.get('youtube_shorts', {})
                            st.code(yt.get('title', ''), language=None)
                            st.code(yt.get('description', ''), language=None)
                            st.write("**🎬 Textos para CapCut:**")
                            for txt in yt.get('capcut_texts', []): st.info(txt)

                        elif platform == "TikTok":
                            tk = pack.get('tiktok', {})
                            st.code(tk.get('caption', ''), language=None)
                            st.write("**⚡ Ganchos visuales:**")
                            for hook in tk.get('capcut_hooks', []): st.warning(hook)
                            st.info(f"💡 **Idea Creativa:** {tk.get('creative_idea')}")

                        elif platform == "Meta (FB/IG) Reels":
                            meta = pack.get('meta_reels', {})
                            st.write("**✍️ Caption para Reels (FB/IG):**")
                            st.code(meta.get('caption', ''), language=None)
                            st.write("**🎬 Textos encimados (CapCut):**")
                            for txt in meta.get('on_screen_texts', []): st.info(txt)
                            with st.expander("📸 Ideas para Stories"):
                                for idea in meta.get('story_ideas', []): st.write(f"• {idea}")

                        elif platform == "Guion de Anuncio (Ads)":
                            ads = pack.get('ads_strategy', {})
                            st.error(f"📺 **Texto en pantalla:** {ads.get('visual_hook')}")
                            st.write("**🎙️ Guion hablado:**")
                            st.info(ads.get('audio_script'))
                            st.write(f"🎵 **Música (No Copyright):** {ads.get('music_type')}")

                    else:
                        st.error("❌ El servidor no respondió correctamente.")
                except Exception as e:
                    st.error(f"❌ Error de conexión: {e}")

# --- PIE DE PÁGINA ---
st.markdown("---")
col_bot1, col_bot2 = st.columns([4, 1])
with col_bot1:
    st.caption("Tridyland Hub v1.1 | Automatización de Marketing para Impresión 3D")
with col_bot2:
    st.write("🐾 Paprika Approved")