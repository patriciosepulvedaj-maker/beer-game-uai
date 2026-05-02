import streamlit as st
import pandas as pd
import altair as alt
import numpy as np
import time
import io
import copy
import json
try:
    import google.generativeai as genai
except ImportError:
    genai = None

from game_logic import BeerGameSession

ROLES_NAMES = ['Minorista', 'Mayorista', 'Distribuidor', 'Fábrica']

# FORZAR FONDO BLANCO COMO PIDIÓ EL USUARIO
st.set_page_config(page_title="🍺 Beer Game (MIT Simulator)", layout="wide", page_icon="🍺", initial_sidebar_state="collapsed")

# --- PRIVACIDAD: BARRERA DE CONTRASEÑA ---
if "authenticated" not in st.session_state:
    st.session_state.authenticated = False
if "role" not in st.session_state:
    st.session_state.role = None
if "student_id" not in st.session_state:
    st.session_state.student_id = ""

if not st.session_state.authenticated:
    st.title("🔒 Acceso Restringido - Simulador UAI")
    st.write("Por favor, ingresa tus credenciales.")
    pwd = st.text_input("Contraseña de la Sesión", type="password")
    rut = st.text_input("Tu RUT / Identificador (Solo para alumnos)")
    
    if st.button("Entrar"):
        if pwd == "UAI_Profesor_2026":
            st.session_state.authenticated = True
            st.session_state.role = "profesor"
            st.session_state.screen = "intro"
            st.rerun()
        elif pwd == "UAI_Alumno_2026":
            if not rut.strip():
                st.error("Los alumnos deben ingresar un RUT o Identificador válido.")
            else:
                st.session_state.authenticated = True
                st.session_state.role = "alumno"
                st.session_state.student_id = rut.strip()
                
                settings = {
                    "modo_juego": "Juego Interactivo Clásico",
                    "semanas": 30,
                    "holding_cost": 0.5,
                    "backlog_cost": 1.0,
                    "dificultad": "Clásico MIT (Fijo -> Salto)",
                    "ai_profile": "Clásico",
                    "human_indices": [0],
                    "visibilidad_total": False,
                    "lt_material": 2,
                    "lt_info": 2
                }
                sess = BeerGameSession(settings)
                st.session_state.session = sess
                st.session_state.settings = settings
                st.session_state.screen = 'game'
                st.rerun()
        else:
            st.error("Contraseña incorrecta.")
    st.stop()
# -----------------------------------------

st.markdown("""
<style>
/* Forzar Fondo Blanco Absoluto */
.stApp, .main { background-color: #ffffff !important; }

/* Estilos de Tarjetas */
.stat-card { background: white; border: 1px solid #e5e7eb; border-radius: 0.5rem; padding: 1rem; box-shadow: 0 1px 3px 0 rgba(0,0,0,0.1); margin-bottom: 1rem; }
.stat-title { font-size: 0.8rem; color: #6b7280; font-weight: 600; text-transform: uppercase; }
.stat-val { font-size: 1.5rem; font-weight: bold; color: #111827; }
.node-card { background: white; border: 2px solid #e5e7eb; border-radius: 0.5rem; padding: 0.75rem; text-align: center; box-shadow: 0 4px 6px -1px rgba(0,0,0,0.1); min-height: 280px; display: flex; flex-direction: column; justify-content: space-between; }
.node-header { padding-bottom: 0.5rem; border-bottom: 1px solid #e5e7eb; margin-bottom: 0.5rem; font-weight: bold; color: #1f2937; }
.node-metric { display: flex; justify-content: space-between; font-size: 0.9em; padding: 2px 0; color: #374151;}
.text-red { color: #dc2626 !important; font-weight: bold; }
.box-arrow { text-align: center; color: #3b82f6; font-size: 1.5rem; margin-top: 3rem; }
.incoming-badge { background-color: #fef08a; border: 1px solid #fde047; color: #854d0e; padding: 2px 6px; border-radius: 4px; font-weight: bold; font-size: 0.8em; }

div[data-testid="stForm"] { border: 2px solid #e5e7eb; background: #f9fafb; }
</style>
""", unsafe_allow_html=True)

if 'screen' not in st.session_state: st.session_state.screen = 'intro'
if 'session' not in st.session_state: st.session_state.session = None
if 'saved_checkpoint' not in st.session_state: st.session_state.saved_checkpoint = None

def reset_game():
    st.session_state.clear()

def rewind_game(target_week):
    if st.session_state.interventions_left > 0 and target_week > 0:
        st.session_state.session = copy.deepcopy(st.session_state.timeline_states[target_week - 1])
        st.session_state.screen = 'game'

def handle_turn():
    sess = st.session_state.session
    user_orders = {}
    
    for i in sess.human_indices:
        key = f"input_ord_{i}"
        val = st.session_state.get(key, 0)
        user_orders[i] = int(val)
        st.session_state[key] = 0
        
    sess.play_turn(user_orders)
    
    # Autoplay para Laboratorio
    modo = st.session_state.settings.get("modo_juego", "Clásico")
    if "Laboratorio" in modo and not sess.is_game_over:
        st.session_state.interventions_left -= 1
        st.session_state.timeline_states = st.session_state.timeline_states[:sess.week - 1]
        
        human_idx_backup = sess.human_indices
        while not sess.is_game_over:
            st.session_state.timeline_states.append(copy.deepcopy(sess))
            sess.human_indices = [] # IA toma el control
            sess.play_turn({})
            sess.human_indices = human_idx_backup
    
    if sess.is_game_over:
        st.session_state.screen = 'reflection'

def get_export_df():
    sess = st.session_state.session
    if not sess.history: return pd.DataFrame()
    data = []
    for h in sess.history:
        row = {
            "Semana": h["week"], "Demanda Cliente": h["demand"],
            "MIN_Inv": h["roles"][0]["inv"], "MIN_Back": h["roles"][0]["back"], "MIN_Pedido": h["roles"][0]["order"], "MIN_Costo_Turno": h["roles"][0]["cost"],
            "MAY_Inv": h["roles"][1]["inv"], "MAY_Back": h["roles"][1]["back"], "MAY_Pedido": h["roles"][1]["order"], "MAY_Costo_Turno": h["roles"][1]["cost"],
            "DIS_Inv": h["roles"][2]["inv"], "DIS_Back": h["roles"][2]["back"], "DIS_Pedido": h["roles"][2]["order"], "DIS_Costo_Turno": h["roles"][2]["cost"],
            "FAB_Inv": h["roles"][3]["inv"], "FAB_Back": h["roles"][3]["back"], "FAB_Pedido": h["roles"][3]["order"], "FAB_Costo_Turno": h["roles"][3]["cost"],
            "Costo Sistema Semanal": sum(r["cost"] for r in h["roles"])
        }
        data.append(row)
    return pd.DataFrame(data)

def generate_dynamic_insights():
    sess = st.session_state.session
    if not sess.history: return []
    insights = []
    
    retailer_orders = [h["roles"][0]["order"] for h in sess.history]
    my_backorders = [h["roles"][0]["back"] for h in sess.history]
    if not retailer_orders: return []
    max_order = max(retailer_orders)
    max_order_week = retailer_orders.index(max_order) + 1
    
    mayorista_backorders = [h["roles"][1]["back"] for h in sess.history]
    fabrica_backorders = [h["roles"][3]["back"] for h in sess.history]
    upstream_crashed = any(b > 0 for b in mayorista_backorders)
    fab_crashed = any(b > 0 for b in fabrica_backorders)
    
    # Análisis 1: Nivel de Servicio (El más importante)
    max_my_back = max(my_backorders)
    if max_my_back > 0:
        insights.append(f"**🚨 Nivel de Servicio Sacrificado:** En tu intento por sobrevivir, dejaste a tu cliente final sin producto llegando a deber **{max_my_back} unidades**. Proteger a la fábrica pidiendo poco no sirve si destruyes la confianza de tu mercado.")
    else:
        insights.append(f"**⭐ Excelente Nivel de Servicio:** Lograste suplir el 100% de la demanda del cliente sin caer en Backorder. Eres un proveedor confiable.")

    # Análisis 2: El Boomerang
    if max_order >= 10:
        if upstream_crashed:
            insights.append(f"**📉 El Boomerang de Acaparamiento:** En la Semana {max_order_week}, un pico de pánico te llevó a pedir {max_order} unidades. Tu 'buen plan' rompió violentamente el stock del Mayorista. Tú mismo causaste tu propia falta de abastecimiento en el Lead Time posterior al secar tu única fuente.")
        else:
            insights.append(f"**⚠️ Alerta de Pánico:** Registraste un pedido anormal de {max_order} cajas en la Semana {max_order_week}. Si la cadena estuviera más frágil, habrías colapsado el abastecimiento.")
    else:
        insights.append(f"**🧘 Estabilidad Individual:** Has mantenido la calma. No se detectaron compras de pánico masivas tempranas.")
            
    # Análisis 3: Impacto en Fábrica
    avg_order = np.mean(retailer_orders)
    demands = [h["demand"] for h in sess.history]
    avg_demand = np.mean(demands)
    
    if avg_order > avg_demand * 1.3:
        percentage = ((avg_order/avg_demand) - 1) * 100
        insights.append(f"**🏭 Latigazo a la Fábrica:** El cliente real promedió {avg_demand:.1f}u, pero pediste {avg_order:.1f}u en promedio. Esta agresividad genera una falsa burbuja inflada en un {percentage:.0f}%, ordenando una sobreproducción ruinosa. " + ("¡Y la fábrica colapsó!" if fab_crashed else ""))
    else:
        insights.append(f"**🤝 Sinergia Promedio:** Tu pedido promedio ({avg_order:.1f}u) se equiparó a la demanda real ({avg_demand:.1f}u). Actuando así, proteges bien a la fábrica.")
        
    return insights

def obtener_analisis_tutor():
    sess = st.session_state.session
    api_key = st.session_state.get('gemini_api_key', '')
    
    if not genai or not api_key:
        return "Error: No se encontró la API Key de Gemini o la librería google-generativeai no está instalada."
        
    genai.configure(api_key=api_key)
    
    # Prepara el payload
    payload = {
        "semanas_jugadas": sess.week,
        "lead_time_producto": st.session_state.settings['lt_material'],
        "lead_time_informacion": st.session_state.settings['lt_info'],
        "costo_mantener": st.session_state.settings['holding_cost'],
        "costo_faltante": st.session_state.settings['backlog_cost'],
        "comportamiento_ia": st.session_state.settings.get('ai_profile', 'Desconocido'),
        "historial": []
    }
    
    for h in sess.history:
        minorista = h["roles"][0] # Asumimos que analizamos al minorista (humano principal)
        payload["historial"].append({
            "semana": h["week"],
            "demanda_cliente": h["demand"],
            "inventario": minorista["inv"],
            "backlog": minorista["back"],
            "pedido_realizado": minorista["order"],
            "costo_acumulado": minorista["cost"]
        })
        
    prompt = f"""
Eres un tutor experto del MIT en Dinámica de Sistemas (basado en Jay Forrester, John Sterman y Peter Senge). 
Se te entrega el historial de una partida del "Beer Distribution Game" jugada por un alumno en el rol de Minorista.

**Instrucciones:**
Analiza el comportamiento del jugador basándote en:
1. Racionalidad Limitada y Pánico (The Panic Trap): ¿El jugador sobre-reaccionó a los backlogs pidiendo cantidades masivas?
2. La Falacia del Inventario en Tránsito (Pipeline Leak): ¿El jugador ignoró que sus pedidos anteriores estaban en camino debido al Lead Time de {payload['lead_time_producto']} semanas?
3. Impacto Sistémico (Efecto Látigo): ¿Su comportamiento amplificó la variabilidad hacia arriba en la cadena?

**Datos de la partida (JSON):**
{json.dumps(payload, indent=2)}

**Formato de Salida Obligatorio (Usa Markdown):**
*   **Resumen Ejecutivo:** Un párrafo tajante sobre su desempeño general.
*   **Diagnóstico de Sobre-reacción:** Identifica (citando semanas específicas) si hubo pánico o aversión al riesgo excesiva.
*   **Análisis del Pipeline:** Explica matemáticamente dónde olvidó calcular el tiempo de entrega.
*   **Lección de Mejora:** Una recomendación técnica (ej. política Base Stock o Suavizamiento) para su próxima intervención.

Sé directo, usa lenguaje técnico de Supply Chain pero formativo.
"""
    try:
        model = genai.GenerativeModel('gemini-1.5-flash')
        response = model.generate_content(prompt)
        return response.text
    except Exception as e:
        # Estrategia a prueba de fallos: buscar dinámicamente qué modelos tiene habilitados la llave
        try:
            valid_models = []
            for m in genai.list_models():
                if 'generateContent' in m.supported_generation_methods:
                    valid_models.append(m.name.replace('models/', ''))
            
            if not valid_models:
                return f"**Error:** Tu API Key es válida, pero tu cuenta no tiene acceso a ningún modelo de IA."
            
            # Buscar el mejor modelo disponible (preferir flash)
            fallback_name = valid_models[0]
            for m in valid_models:
                if 'flash' in m and '8b' not in m: # prefer standard flash
                    fallback_name = m
                    break
                    
            model = genai.GenerativeModel(fallback_name)
            response = model.generate_content(prompt)
            return response.text
            
        except Exception as fallback_e:
            lista_modelos = ", ".join(valid_models) if 'valid_models' in locals() else "Desconocido"
            return f"**Error de comunicación.** Modelos en tu cuenta: {lista_modelos}. Detalle técnico: {str(fallback_e)}"

def get_player_df():
    sess = st.session_state.session
    if not sess.history: return pd.DataFrame()
    data = []
    
    human_roles = sess.human_indices
    
    for h in sess.history:
        row = {"Semana": h["week"], "Demanda Cliente": h["demand"]}
        if st.session_state.get("role") == "alumno":
            row["Identificador_Alumno"] = st.session_state.get("student_id", "Desc")
        for role_idx in human_roles:
            role_prefix = ROLES_NAMES[role_idx][:3].upper()
            r_data = h["roles"][role_idx]
            row[f"{role_prefix}_Inventario"] = r_data["inv"]
            row[f"{role_prefix}_Backlog"] = r_data["back"]
            row[f"{role_prefix}_Pedido"] = r_data["order"]
            row[f"{role_prefix}_Costo"] = r_data["cost"]
        data.append(row)
    return pd.DataFrame(data)

def download_excel_consolidated():
    df = get_export_df()
    if df.empty: return None
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, index=False, sheet_name='Consolidado_Profesor')
    return output.getvalue()

def download_excel_player():
    df = get_player_df()
    if df.empty: return None
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, index=False, sheet_name='Reporte_Jugador')
    return output.getvalue()

# -----------------
# PANTALLA INTRODUCCIÓN
# -----------------
if st.session_state.screen == 'intro':
    st.title("🍺 Beer Distribution Game - Configurador")
    st.info("Antes de iniciar, parametriza la simulación según tu necesidad pedagógica.")
    
    if st.button("📊 Ir al Dashboard de Profesores (Corrección Masiva)", type="secondary"):
        st.session_state.screen = 'admin_dashboard'
        st.rerun()
        
    with st.form("config_form"):
        st.subheader("⚙️ Parámetros del Simulador")
        
        c1, c2, c3 = st.columns(3)
        with c1:
            modo_juego = st.selectbox("Modo de Juego", ["Juego Interactivo Clásico", "Laboratorio: Máquina del Tiempo (Sandbox)"])
            
            opciones_mision = [
                "Clásico MIT (Fijo -> Salto)", 
                "Misión: Promoción Relámpago (Pico en sem 8)",
                "Misión: Crecimiento Estacional",
                "Misión: Contracción de Mercado",
                "Aleatoria Moderada", 
                "Aleatoria Extrema"
            ]
            diff = st.selectbox("Comportamiento Demanda", opciones_mision)
            
            if "Relámpago" in diff:
                st.caption("⚡ Demanda estable con un pico masivo temporal. Mide la resistencia al pánico.")
            elif "Crecimiento" in diff:
                st.caption("📈 Demanda crece semana a semana hasta estabilizarse arriba. Mide el control de backlog.")
            elif "Contracción" in diff:
                st.caption("📉 Demanda cae bruscamente a la mitad. Mide el frenado del 'Pipeline'.")
            elif "Clásico" in diff:
                st.caption("📚 El experimento original. Salto repentino de 4 a 8 unidades.")
            
            semanas = st.number_input("Semanas de Juego", min_value=10, max_value=100, value=30, step=1)
            lt_mat = st.number_input("Lead Time Producto (Semanas)", min_value=1, max_value=5, value=2, step=1)
            
        with c2:
            ai_profile = st.selectbox("Comportamiento IA (Resto de la Cadena)", ["Clásico", "Nervioso", "Conservador"])
            hold_c = st.number_input("Costo Mantener (Holding) $", min_value=0.0, value=0.5, step=0.1)
            back_c = st.number_input("Costo Faltante (Backlog) $", min_value=0.0, value=1.0, step=0.1)
            lt_info = st.number_input("Lead Time Información (Sem.)", min_value=1, max_value=5, value=2, step=1)
            
        with c3:
            visibilidad = st.radio("Transparencia de Datos", [
                "Mostrar Todo (Transparente - Didáctico)", 
                "Solo ver Mi Nodo (Opaco - Juego Real)"
            ])
            humanos_str = st.multiselect("Jugadores Humanos participando:", ROLES_NAMES, default=["Minorista"])
            max_interventions = st.number_input("Cuota de Intervenciones (Laboratorio)", min_value=1, max_value=10, value=3, step=1)
            
        st.markdown("---")
        st.subheader("🤖 Integración Tutor IA (Opcional)")
        api_key_input = st.text_input("Gemini API Key (Para activar análisis profundos de MIT Supply Chain)", type="password")
            
        submit = st.form_submit_button("▶️ Generar Simulación", use_container_width=True)
        
        if submit:
            st.session_state.gemini_api_key = api_key_input
            human_indices = [ROLES_NAMES.index(h) for h in humanos_str]
            if len(human_indices) == 0:
                st.error("Debes seleccionar al menos 1 jugador.")
            else:
                settings = {
                    "modo_juego": modo_juego,
                    "semanas": semanas,
                    "holding_cost": hold_c,
                    "backlog_cost": back_c,
                    "dificultad": diff,
                    "ai_profile": ai_profile,
                    "human_indices": human_indices,
                    "visibilidad_total": "Mostrar Todo" in visibilidad,
                    "lt_material": lt_mat,
                    "lt_info": lt_info
                }
                sess = BeerGameSession(settings)
                
                # Fast-forward para Laboratorio de Escenarios
                if "Laboratorio" in modo_juego:
                    st.session_state.timeline_states = []
                    while not sess.is_game_over:
                        st.session_state.timeline_states.append(copy.deepcopy(sess))
                        sess.human_indices = []
                        sess.play_turn({})
                        sess.human_indices = human_indices
                    
                    st.session_state.interventions_left = max_interventions
                    st.session_state.session = sess
                    st.session_state.settings = settings
                    st.session_state.screen = 'reflection'
                    st.rerun()
                    
                st.session_state.session = sess
                st.session_state.settings = settings
                st.session_state.screen = 'game'
                st.rerun()

# -----------------
# PANTALLA JUEGO
# -----------------
elif st.session_state.screen == 'game':
    sess = st.session_state.session
    # Failsafe: Si Streamlit hace hot-reload y mantiene una sesión con código viejo en caché
    if not hasattr(sess, 'costs_accumulated'):
        st.session_state.clear()
        st.rerun()

    sett = st.session_state.settings
    current_demand = sess.history[-1]["demand"] if sess.history else 4
    
    # Barra Superior
    cHeader1, cHeader2, cHeader3, cHeader4, cHeader5 = st.columns([1.2, 1, 1, 1, 0.8])
    with cHeader1:
        st.header(f"Semana {sess.week} / {sett['semanas']}")
        st.caption("Efecto Látigo en Marcha...")
    with cHeader2: 
        st.markdown(f'<div class="stat-card"><div class="stat-title">Demanda Inicial Cliente</div><div class="stat-val text-green-600">{current_demand}u 🛒</div></div>', unsafe_allow_html=True)
    with cHeader3: 
        costo_humanos = sum(sess.costs_accumulated[i] for i in sett['human_indices'])
        st.markdown(f'<div class="stat-card" style="border-bottom: 4px solid #ef4444;"><div class="stat-title">Tu Costo</div><div class="stat-val text-red-600">${costo_humanos:.2f}</div></div>', unsafe_allow_html=True)
    with cHeader4: 
        st.markdown(f'<div class="stat-card" style="border-bottom: 4px solid #111827;"><div class="stat-title">Costo Total</div><div class="stat-val">${sum(sess.costs_accumulated):.2f}</div></div>', unsafe_allow_html=True)
    with cHeader5:
        if st.session_state.get('role') != 'alumno':
            st.button("⚙️ Reconfigurar", on_click=reset_game, use_container_width=True)
    
    st.write("---")
    
    # Tablero Central (Desde Fábrica hasta Minorista visualmente)
    ui_cols = st.columns([2, 0.5, 2, 0.5, 2, 0.5, 2])
    render_indices = [3, 2, 1, 0] # 3:Fábrica -> 2:Distribuidor -> 1:Mayorista -> 0:Minorista
    icons = ["🏭", "📦", "📦", "👤"]
    
    for i, role_index in enumerate(render_indices):
        col_card = ui_cols[i * 2]
        incoming_phys = sum(s["amount"] for s in sess.shipments if s["toRole"] == role_index)
        diag = sess.get_role_diagnostics(role_index)
        
        is_human = role_index in sett['human_indices']
        show_data = is_human or sett['visibilidad_total']
        
        if i > 0:
            with ui_cols[(i * 2) - 1]:
                shipments_to_me = [s for s in sess.shipments if s["toRole"] == role_index]
                shipments_to_me.sort(key=lambda x: x['weeksLeft'])
                b_lines = [f"en {s['weeksLeft']}sem: <b>{s['amount']}u</b>" for s in shipments_to_me]
                b_html = "".join([f"<div style='font-size:0.5em; color:#6b7280; line-height:1.1;'>{line}</div>" for line in b_lines])
                st.markdown(f'<div class="box-arrow" style="margin-top:2rem;">➡️<br><span class="incoming-badge">{incoming_phys}u</span><div style="margin-top:4px;">{b_html}</div></div>', unsafe_allow_html=True)
        else:
            with col_card: st.caption(f"Tránsito Fabricación: {incoming_phys}u")
            
        with col_card:
            emoji = diag['moodEmoji'] if show_data else "🤫"
            
            with st.container(border=True):
                st.markdown(f"#### {icons[i]} {ROLES_NAMES[role_index]} {emoji}")
                
                if show_data:
                    stress_str = " | ".join([f"{s['icon']} {s['label']}" for s in diag["stressors"]])
                    if stress_str:
                        st.caption(f"**Status:** {stress_str}")
                    
                    if sess.backorders[role_index] > 0:
                        st.error(f"Backorder: {sess.backorders[role_index]}", icon="🚨")
                    
                    st.metric("📦 Inventario Disp.", sess.inventory[role_index])
                    st.caption(f"Último Pedido emitido: **{sess.last_orders[role_index]}**")
                    
                    lt_mat_val = sett.get('lt_material', 2)
                    st.caption(f"Recibido (-{lt_mat_val} sem): **{sess.last_received[role_index]}**")
                else:
                    st.metric("📦 Inventario Disp.", "???")
                    st.caption("Opaco (Modo Competitivo)")
                    
            if is_human:
                st.number_input(f"Anotar Pedido ({ROLES_NAMES[role_index]})", min_value=0, max_value=5000, value=0, key=f"input_ord_{role_index}")
                
    st.write("---")
    c_btn1, c_btn2, c_btn3 = st.columns([1,2,1])
    with c_btn2:
        st.button("📦 ENVIAR TURNOS DE ESTA SEMANA", type="primary", use_container_width=True, on_click=handle_turn)

# -----------------
# PANTALLA REFLEXIÓN
# -----------------
elif st.session_state.screen == 'reflection':
    sess = st.session_state.session
    st.balloons()
    st.title("📊 Resumen Gerencial Integrado (BI)")
    
    df = pd.DataFrame(sess.history)
    demands = df["demand"].tolist()
    orders_factory = [r["roles"][3]["order"] for r in sess.history]
    
    var_demand = np.var(demands)
    var_factory = np.var(orders_factory)
    ratio = var_factory / var_demand if var_demand > 0 else 0
    
    st.markdown(f"""
    <div style="padding:15px; background:#f8fafc; border: 1px solid #e2e8f0; border-left: 5px solid {'#ef4444' if ratio > 1 else '#10b981'}; margin-bottom:20px; border-radius: 8px;">
        <h3>Ratio de Amplificación (Bullwhip Effect): {ratio:.2f}x</h3>
        <p>Si el ratio es superior a 1, quedó comprobado que la volatilidad introducida por la cadena es mucho mayor que la del cliente final.</p>
    </div>
    """, unsafe_allow_html=True)
    
    t1, t2, t3 = st.tabs(["📉 Curvas de Amplificación", "📋 Tabla Integrada de Datos", "📝 Análisis de Cierre y Excel"])
    
    with t1:
        st.subheader("Impacto Latigazo (Pedidos en el Tiempo vs Demanda Real)")
        chart_data = []
        for h in sess.history:
            chart_data.append({"Semana": h["week"], "Actor": "Demanda", "Unidades": h["demand"]})
            for i in range(4):
                chart_data.append({"Semana": h["week"], "Actor": ROLES_NAMES[i], "Unidades": h["roles"][i]["order"]})
            
        c = alt.Chart(pd.DataFrame(chart_data)).mark_line(opacity=0.8, point=True, strokeWidth=2).encode(
            x='Semana:O', y='Unidades:Q', color='Actor:N', tooltip=['Semana', 'Actor', 'Unidades']
        ).properties(height=450)
        st.altair_chart(c, use_container_width=True)
        
        st.subheader("Sobrecosto Generado por Actor (USD)")
        df_costs = pd.DataFrame({"Actor": ROLES_NAMES, "Acumulado": sess.costs_accumulated})
        st.bar_chart(df_costs.set_index("Actor"))
        
    with t2:
        st.subheader("Visualizador de Movimientos (Data Explorer)")
        st.info("Pasa el mouse sobre el borde de la tabla para ver el botón de descarga rápida nativa.")
        _df = get_export_df()
        st.dataframe(_df, use_container_width=True, height=400)
        
    with t3:
        colA, colB = st.columns([3, 2])
        with colA:
            st.markdown("### 🧠 Insights Generados (Análisis Post-Partida)")
            insights = generate_dynamic_insights()
            if insights:
                for ins in insights:
                    st.info(ins)
            else:
                st.warning("Completa al menos algunas semanas para obtener tu diagnóstico algorítmico.")
                
            if st.session_state.get('gemini_api_key'):
                st.markdown("---")
                if st.button("🤖 Solicitar Análisis Profundo al Tutor IA", type="primary", use_container_width=True):
                    with st.spinner("El Tutor está analizando tu comportamiento sistémico..."):
                        tutor_feedback = obtener_analisis_tutor()
                    st.markdown("### 🎓 Análisis del Tutor MIT")
                    st.markdown(tutor_feedback)
        with colB:
            p_data = download_excel_player()
            if p_data:
                fname = f"reporte_{st.session_state.get('student_id', 'alumno')}_beergame.xlsx" if st.session_state.get('role') == 'alumno' else "reporte_alumno_beergame.xlsx"
                st.download_button(
                    label="📥 Descargar Mi Reporte (Alumno) Excel",
                    data=p_data,
                    file_name=fname,
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    use_container_width=True
                )
            
            c_data = download_excel_consolidated()
            if c_data:
                st.download_button(
                    label="🔐 Extraer Consolidado (Profesor) Excel",
                    data=c_data,
                    file_name=f"reporte_profesor_beergame.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    use_container_width=True
                )
            modo = st.session_state.settings.get("modo_juego", "Clásico")
            if "Laboratorio" in modo:
                st.markdown("---")
                st.markdown("### 🚀 Máquina del Tiempo")
                st.caption(f"🔋 Intervenciones Restantes: **{st.session_state.interventions_left}** / {st.session_state.settings.get('max_interventions', 3)}")
                
                if st.session_state.interventions_left > 0:
                    target_w = st.slider("Viajar en el tiempo a la Semana:", min_value=1, max_value=st.session_state.settings['semanas']-1, value=10)
                    if st.button("⏪ Viajar y Alterar Historia", type="primary", use_container_width=True):
                        rewind_game(target_w)
                else:
                    st.error("Has agotado tu presupuesto de intervenciones.")
            st.button("🔄 Reiniciar Laboratorio", on_click=reset_game, use_container_width=True)

# -----------------
# PANTALLA ADMIN DASHBOARD
# -----------------
elif st.session_state.screen == 'admin_dashboard':
    st.title("📊 Dashboard Consolidado del Curso")
    st.info("Sube aquí los reportes Excel individuales que enviaron tus alumnos.")
    
    if st.button("⬅️ Volver al Configurador"):
        st.session_state.screen = 'intro'
        st.rerun()
        
    uploaded_files = st.file_uploader("Archivos Excel de Alumnos", type="xlsx", accept_multiple_files=True)
    
    if uploaded_files:
        all_data = []
        student_dfs = {}
        for file in uploaded_files:
            try:
                df = pd.read_excel(file)
                if "Identificador_Alumno" in df.columns:
                    student_id = str(df["Identificador_Alumno"].iloc[0])[:30] # Excel sheet name limit is 31 chars
                    
                    total_cost = df["MIN_Costo"].sum() if "MIN_Costo" in df.columns else 0
                    total_backorders = df["MIN_Backlog"].sum() if "MIN_Backlog" in df.columns else 0
                    
                    demands = df["Demanda Cliente"].tolist() if "Demanda Cliente" in df.columns else []
                    orders = df["MIN_Pedido"].tolist() if "MIN_Pedido" in df.columns else []
                    
                    avg_order = np.mean(orders) if len(orders) > 0 else 0
                    var_dem = np.var(demands) if len(demands) > 0 else 1
                    var_ord = np.var(orders) if len(orders) > 0 else 0
                    bullwhip = var_ord / var_dem if var_dem > 0 else 0
                    
                    all_data.append({
                        "RUT": student_id,
                        "Costo_Total": total_cost,
                        "Efecto_Latigo": round(bullwhip, 2),
                        "Total_Backorders": total_backorders,
                        "Promedio_Pedidos": round(avg_order, 1)
                    })
                    
                    student_dfs[student_id] = df
            except Exception as e:
                st.error(f"Error procesando {file.name}: {e}")
                
        if all_data:
            results_df = pd.DataFrame(all_data).sort_values("Costo_Total")
            
            st.markdown("### 🏆 Ranking y Métricas de Desempeño")
            st.dataframe(results_df, use_container_width=True)
            
            c1, c2 = st.columns(2)
            with c1:
                st.markdown("#### Costo Total por Alumno")
                c_cost = alt.Chart(results_df).mark_bar().encode(
                    x=alt.X("RUT:N", sort="-y"),
                    y="Costo_Total:Q",
                    color=alt.Color("Costo_Total:Q", scale=alt.Scale(scheme="reds")),
                    tooltip=["RUT", "Costo_Total", "Total_Backorders"]
                ).properties(height=300)
                st.altair_chart(c_cost, use_container_width=True)
            with c2:
                st.markdown("#### Efecto Látigo (Bullwhip Ratio)")
                c_bw = alt.Chart(results_df).mark_bar().encode(
                    x=alt.X("RUT:N", sort="-y"),
                    y="Efecto_Latigo:Q",
                    color=alt.Color("Efecto_Latigo:Q", scale=alt.Scale(scheme="oranges")),
                    tooltip=["RUT", "Efecto_Latigo", "Promedio_Pedidos"]
                ).properties(height=300)
                st.altair_chart(c_bw, use_container_width=True)
                
            output = io.BytesIO()
            with pd.ExcelWriter(output, engine='openpyxl') as writer:
                # Escribir la hoja de resumen primero
                results_df.to_excel(writer, index=False, sheet_name='Resumen_Metricas')
                # Escribir cada dataframe individual en una hoja propia
                for s_id, s_df in student_dfs.items():
                    # Asegurar nombre válido para pestaña excel
                    clean_id = "".join([c if c.isalnum() else "_" for c in s_id])[:31]
                    s_df.to_excel(writer, index=False, sheet_name=clean_id)
            st.download_button("📥 Descargar Libro Consolidado (Resumen + Detalle por Alumno)", data=output.getvalue(), file_name="BeerGame_Consolidado_Completo.xlsx", mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
