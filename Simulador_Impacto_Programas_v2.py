import streamlit as st
import pandas as pd
import sqlite3
import numpy as np
import plotly.graph_objects as go
import plotly.express as px
from fpdf import FPDF
from datetime import datetime
import io

# --- CONFIGURAÇÕES DE ESCALA ---
STEP_MONEY = 10.0
STEP_MACRO_MONEY = 1000.0
STEP_RESOURCE = 1

# --- DATABASE ENGINE ---
def init_db():
    conn = sqlite3.connect('pmo_master_enterprise.db', check_same_thread=False)
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS recursos (
                 id INTEGER PRIMARY KEY AUTOINCREMENT, 
                 projeto TEXT, funcao TEXT, custo_h REAL, horas INTEGER, subtotal REAL)''')
    c.execute('''CREATE TABLE IF NOT EXISTS cenarios (
                 id INTEGER PRIMARY KEY AUTOINCREMENT,
                 projeto TEXT, nome_cenario TEXT, impacto_p95 REAL, margem REAL, data TEXT)''')
    conn.commit()
    return conn

db_conn = init_db()

# --- FUNÇÕES CORE ---
def format_currency(val):
    return f"R$ {val:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")

def run_monte_carlo(o, m, p, n=5000):
    if o >= p: return float(m), float(m)
    sims = np.random.triangular(o, m, p, n)
    return float(np.mean(sims)), float(np.percentile(sims, 95))

# Classe PDF Robusta
class ExecutivePDF(FPDF):
    def header(self):
        self.set_font('Arial', 'B', 15)
        self.set_text_color(0, 51, 102)
        self.cell(0, 10, 'PARECER TECNICO DE IMPACTO ECONOMICO - PMO MV', 0, 1, 'R')
        self.ln(10)

# --- INTERFACE ---
st.set_page_config(page_title="MV PMO Intelligence PRO", layout="wide")

with st.sidebar:
    st.header("⚙️ Parâmetros do Programa")
    proj = st.selectbox("Selecione o Projeto", [" ", "UNIMED SERRA GAUCHA", "INS", "CLINICA GIRASSOL", "EINSTEIN", "RHP"])
    receita_net = st.number_input("Receita Líquida (R$)", value=1000.0, step=STEP_MACRO_MONEY)
    custo_eac_base = st.number_input("Custo Atual EAC (R$)", value=1000.0, step=STEP_MACRO_MONEY)

tab1, tab2, tab3 = st.tabs(["🚀 Simulação Ativa", "📊 Sensibilidade", "📚 Hub de Cenários"])

with tab1:
    # 1. CATEGORIAS DE IMPACTO
    st.subheader("1. Categorias de Impacto Técnico")
    cat_impacto = st.selectbox("Causa Raiz:", ["Replanejamento (Rollout)", "Retrabalho (Escopo)", "Instabilidade (Bugs)", "Infraestrutura (Ociosidade)"])
    
    impacto_calculado_cat = 0.0
    with st.container(border=True):
        col_c1, col_c2, col_c3 = st.columns(3)
        if cat_impacto == "Replanejamento (Rollout)":
            u = col_c1.number_input("Unidades Restantes", value=10, step=STEP_RESOURCE)
            b = col_c2.number_input("Burn Rate Mensal", value=1000.0, step=STEP_MACRO_MONEY)
            p_pace = col_c3.slider("Pace (Un/Mês)", 0.5, 5.0, 2.0)
            impacto_calculado_cat = (u / p_pace) * b
        elif cat_impacto == "Retrabalho (Escopo)":
            h = col_c1.number_input("H/H Estimada", value=150, step=STEP_RESOURCE)
            c = col_c2.number_input("Custo H/H", value=150.0, step=STEP_MONEY)
            impacto_calculado_cat = h * c
        elif cat_impacto == "Instabilidade (Bugs)":
            q = col_c1.number_input("Qtd de Chamados", value=10, step=STEP_RESOURCE)
            t = col_c2.number_input("Média Horas/Bug", value=8, step=STEP_RESOURCE)
            impacto_calculado_cat = q * t * 145.0
        elif cat_impacto == "Infraestrutura (Ociosidade)":
            d = col_c1.number_input("Dias de Bloqueio", value=5, step=STEP_RESOURCE)
            cd = col_c2.number_input("Custo Diário", value=1000.0, step=STEP_MACRO_MONEY)
            impacto_calculado_cat = d * cd

    # 2. GESTÃO DE RECURSOS (CRUD)
    st.subheader("2. Gestão de Recurso Adicional")
    with st.expander("➕ Vincular Novo Recurso"):
        with st.form("add_rec", clear_on_submit=True):
            f1, f2, f3 = st.columns([2,1,1])
            func = f1.selectbox("Função", ["Consultor Jr","Consultor Pl","Consultor Sr","Analista Jr", "Analista Pl","Analista Sr", "Gerente de projeto Jr","Gerente de projeto Pl","Gerente de projeto Sr", "Desenvolvedor Jr", "Desenvolvedor Pl", "Desenvolvedor Sr"])
            custo_h = f2.number_input("Custo/H", value=150.0, step=STEP_MONEY)
            horas_a = f3.number_input("Horas", value=10, step=STEP_RESOURCE)
            if st.form_submit_button("Adicionar"):
                db_conn.execute("INSERT INTO recursos (projeto, funcao, custo_h, horas, subtotal) VALUES (?,?,?,?,?)",
                             (proj, func, custo_h, horas_a, custo_h * horas_a))
                db_conn.commit()
                st.rerun()

    df_rec = pd.read_sql_query(f"SELECT * FROM recursos WHERE projeto = '{proj}'", db_conn)
    custo_staff = df_rec['subtotal'].sum() if not df_rec.empty else 0.0
    
    if not df_rec.empty:
        for idx, row in df_rec.iterrows():
            with st.container(border=True):
                c1, c2, c3, c4 = st.columns([2,1,1,0.5])
                c1.write(f"**{row['funcao']}**")
                c2.write(f"{row['horas']}h x {format_currency(row['custo_h'])}")
                c3.write(f"**{format_currency(row['subtotal'])}**")
                if c4.button("🗑️", key=f"del_{row['id']}"):
                    db_conn.execute(f"DELETE FROM recursos WHERE id = {row['id']}")
                    db_conn.commit()
                    st.rerun()

    # 3. RESULTADOS E PDF (FIXED)
    st.divider()
    m_nominal = impacto_calculado_cat + custo_staff
    val_mean, val_p95 = run_monte_carlo(m_nominal * 0.9, m_nominal, m_nominal * 1.5)
    margem_f = (1 - ((custo_eac_base + val_p95) / receita_net)) * 100 if receita_net > 0 else 0

    res1, res2 = st.columns(2)
    with res1:
        st.metric("Impacto P95 (Teto)", format_currency(val_p95))
        st.metric("Margem Projetada", f"{margem_f:.2f}%")
        
        # MOTOR DE PDF CORRIGIDO
        if st.button("📑 Gerar Relatório PDF"):
            pdf = ExecutivePDF()
            pdf.add_page()
            pdf.set_font("Arial", 'B', 12)
            pdf.cell(0, 10, f"Projeto: {proj} | Categoria: {cat_impacto}", ln=1)
            pdf.cell(0, 10, f"Impacto P95: {format_currency(val_p95)}", ln=1)
            pdf.cell(0, 10, f"Margem Final: {margem_f:.2f}%", ln=1)
            
            # Gerando bytes de forma segura para o Streamlit
            pdf_output = pdf.output(dest='S')
            if isinstance(pdf_output, str):
                pdf_bytes = pdf_output.encode('latin-1')
            else:
                pdf_bytes = bytes(pdf_output)
            
            st.download_button("📥 Baixar Parecer", data=pdf_bytes, file_name="Parecer_PMO.pdf", mime="application/pdf")

    with res2:
        fig_radar = go.Figure()
        fig_radar.add_trace(go.Scatterpolar(r=[1,1,1,1], theta=['Custo','Prazo','Escopo','Custo'], fill='toself', name='Baseline'))
        fig_radar.add_trace(go.Scatterpolar(r=[val_p95/(m_nominal*1.2 if m_nominal>0 else 1), 1.3, 1.2, 1.1], theta=['Custo','Prazo','Escopo','Custo'], fill='toself', name='Cenário', line_color='red'))
        fig_radar.update_layout(polar=dict(radialaxis=dict(visible=True, range=[0, 2])), height=350)
        st.plotly_chart(fig_radar, use_container_width=True)

with tab2:
    st.header("📊 Composição do Impacto")
    data_s = [{'Origem': cat_impacto, 'Valor': impacto_calculado_cat}]
    if not df_rec.empty:
        for _, r in df_rec.iterrows(): data_s.append({'Origem': r['funcao'], 'Valor': r['subtotal']})
    st.plotly_chart(px.pie(pd.DataFrame(data_s), values='Valor', names='Origem', hole=0.4))

with tab3:
    st.header("📚 Hub de Cenários")
    nome_s = st.text_input("Nome do Snapshot:")
    if st.button("💾 Salvar"):
        db_conn.execute("INSERT INTO cenarios (projeto, nome_cenario, impacto_p95, margem, data) VALUES (?,?,?,?,?)",
                     (proj, nome_s, val_p95, margem_f, datetime.now().strftime("%d/%m %H:%M")))
        db_conn.commit()
    st.dataframe(pd.read_sql_query(f"SELECT * FROM cenarios WHERE projeto = '{proj}'", db_conn), use_container_width=True)
