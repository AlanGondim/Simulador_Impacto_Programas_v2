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

# --- DATABASE ---
def init_db():
    conn = sqlite3.connect('pmo_master.db', check_same_thread=False)
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS recursos (id INTEGER PRIMARY KEY AUTOINCREMENT, 
                 projeto TEXT, funcao TEXT, senioridade TEXT, custo_h REAL, horas INTEGER, subtotal REAL)''')
    c.execute('''CREATE TABLE IF NOT EXISTS cenarios (id INTEGER PRIMARY KEY AUTOINCREMENT,
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

class ExecutivePDF(FPDF):
    def header(self):
        self.set_font('Arial', 'B', 15)
        self.set_text_color(0, 51, 102)
        self.cell(0, 10, 'PARECER TECNICO DE IMPACTO ECONOMICO', 0, 1, 'R')
        self.ln(10)

# --- INTERFACE ---
st.title("🛡️ MV PMO Decision Intelligence PRO")

with st.sidebar:
    st.title("⚙️ Configuração Master")
    proj = st.selectbox("Programa", ["UNIMED SERRA GAUCHA", "INS", "CLINICA GIRASSOL", "EINSTEIN", "RHP"])
    receita_net = st.number_input("Receita Líquida (R$)", value=4719147.0, step=STEP_MACRO_MONEY)
    custo_eac_base = st.number_input("Custo Atual EAC (R$)", value=4963246.0, step=STEP_MACRO_MONEY)

tab1, tab2, tab3 = st.tabs(["🚀 Simulação Ativa", "📊 Sensibilidade", "📚 Hub de Cenários"])

with tab1:
    with st.expander("👥 Gestão de Recursos (Alocação)", expanded=True):
        with st.form("form_rec"):
            f1, f2, f3, f4 = st.columns([2,1,1,1])
            func = f1.selectbox("Função", ["Consultor", "Analista", "Arquiteto", "Dev", "PMO"])
            ch = f3.number_input("Custo/Hora", value=130.0, step=STEP_MONEY)
            hr = f4.number_input("Qtd Horas", value=160, step=STEP_RESOURCE)
            if st.form_submit_button("Confirmar Alocação"):
                db_conn.execute("INSERT INTO recursos (projeto, funcao, senioridade, custo_h, horas, subtotal) VALUES (?,?,'Sr',?,?,?)",
                             (proj, func, ch, hr, ch*hr))
                db_conn.commit()
                st.rerun()
        
        df_rec = pd.read_sql_query(f"SELECT * FROM recursos WHERE projeto = '{proj}'", db_conn)
        if not df_rec.empty:
            st.dataframe(df_rec[['funcao', 'custo_h', 'horas', 'subtotal']], use_container_width=True)
            if st.button("🗑️ Limpar Tudo"):
                db_conn.execute(f"DELETE FROM recursos WHERE projeto = '{proj}'")
                db_conn.commit()
                st.rerun()

    # Cálculo de Impacto
    custo_nominal = df_rec['subtotal'].sum() if not df_rec.empty else 0.0
    o = st.sidebar.number_input("Cenário Otimista", value=custo_nominal * 0.9, step=STEP_MONEY)
    p = st.sidebar.number_input("Cenário Pessimista", value=custo_nominal * 1.5, step=STEP_MONEY)
    
    val_pert, val_p95 = run_monte_carlo(o, custo_nominal, p)
    margem_final = (1 - ((custo_eac_base + val_p95) / receita_net)) * 100 if receita_net > 0 else 0

    c1, c2, c3 = st.columns(3)
    c1.metric("Custo P95", format_currency(val_p95))
    c2.metric("Margem Projetada", f"{margem_final:.2f}%")
    
    # Triângulo de Ferro
    cost_idx = val_p95 / (custo_nominal * 1.2) if custo_nominal > 0 else 1.0
    fig_radar = go.Figure()
    fig_radar.add_trace(go.Scatterpolar(r=[1,1,1,1], theta=['Custo','Prazo','Escopo','Custo'], fill='toself', name='Base'))
    fig_radar.add_trace(go.Scatterpolar(r=[cost_idx, 1.3, 1.2, cost_idx], theta=['Custo','Prazo','Escopo','Custo'], fill='toself', name='Impacto', line_color='red'))
    fig_radar.update_layout(polar=dict(radialaxis=dict(visible=True, range=[0, 2])), height=350)
    st.plotly_chart(fig_radar, use_container_width=True)

    # Botão de PDF Corrigido
    if st.button("📑 Gerar Relatório PDF"):
        pdf = ExecutivePDF()
        pdf.add_page()
        pdf.set_font("Arial", 'B', 12)
        pdf.cell(0, 10, f"Projeto: {proj}", ln=1)
        pdf.cell(0, 10, f"Impacto P95: {format_currency(val_p95)} | Margem: {margem_final:.2f}%", ln=1)
        
        pdf_bytes = pdf.output(dest='S').encode('latin-1', 'replace') if hasattr(pdf, 'output') else b""
        st.download_button("📥 Baixar Parecer", data=pdf_bytes, file_name="Relatorio_PMO.pdf", mime="application/pdf")

with tab2:
    st.header("🔍 Análise de Sensibilidade")
    if not df_rec.empty:
        fig_pie = px.pie(df_rec, values='subtotal', names='funcao', title='Distribuição de Impacto por Recurso', hole=.4)
        st.plotly_chart(fig_pie)
        st.write("**Parecer:** O recurso que mais contribui para a erosão da margem é o **{}**.".format(df_rec.loc[df_rec['subtotal'].idxmax(), 'funcao']))
    else:
        st.info("Adicione recursos para ver a análise de sensibilidade.")

with tab3:
    st.header("📚 Hub de Cenários")
    nome_cen = st.text_input("Salvar simulação atual como:", "Cenário Alfa")
    if st.button("💾 Gravar Cenário"):
        db_conn.execute("INSERT INTO cenarios (projeto, nome_cenario, impacto_p95, margem, data) VALUES (?,?,?,?,?)",
                     (proj, nome_cen, val_p95, margem_final, datetime.now().strftime("%d/%m %H:%M")))
        db_conn.commit()
    
    df_h = pd.read_sql_query(f"SELECT * FROM cenarios WHERE projeto = '{proj}'", db_conn)
    st.table(df_h)
