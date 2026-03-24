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
    conn = sqlite3.connect('pmo_master_vfinal.db', check_same_thread=False)
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS recursos (id INTEGER PRIMARY KEY AUTOINCREMENT, 
                 projeto TEXT, funcao TEXT, custo_h REAL, horas INTEGER, subtotal REAL)''')
    c.execute('''CREATE TABLE IF NOT EXISTS cenarios (id INTEGER PRIMARY KEY AUTOINCREMENT,
                 projeto TEXT, nome_cenario TEXT, impacto_p95 REAL, margem REAL, data TEXT)''')
    conn.commit()
    return conn

db_conn = init_db()

# --- HELPER FUNCTIONS ---
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
        self.cell(0, 10, 'PARECER TECNICO DE IMPACTO ECONOMICO - PMO MV', 0, 1, 'R')
        self.ln(10)

# --- SIDEBAR: MASTER DATA ---
with st.sidebar:
    st.image("Logomarca MV Atualizada.png", width=150)
    st.title("⚙️ Governança de Dados")
    proj = st.selectbox("Programa", ["UNIMED SERRA GAUCHA", "INS", "CLINICA GIRASSOL", "EINSTEIN", "RHP"])
    receita_net = st.number_input("Receita Líquida (R$)", value=4719147.0, step=STEP_MACRO_MONEY)
    custo_eac_base = st.number_input("Custo Atual EAC (R$)", value=4963246.0, step=STEP_MACRO_MONEY)

# --- MAIN INTERFACE ---
st.title("🛡️ MV PMO Decision Intelligence PRO")

t1, t2, t3 = st.tabs(["🚀 Simulação Ativa", "📊 Sensibilidade", "📚 Hub de Cenários"])

with t1:
    # 1. CATEGORIAS DE IMPACTO (O coração da sua solicitação)
    st.subheader("1. Análise de Causa Raiz & Impacto Direto")
    cat_impacto = st.selectbox("Categoria do Incidente:", 
                              ["Replanejamento (Rollout)", "Retrabalho (Escopo)", "Instabilidade (Bugs)", "Infraestrutura (Ociosidade)"])
    
    impacto_cat_nominal = 0.0

    with st.container(border=True):
        c1, c2, c3 = st.columns(3)
        if cat_impacto == "Replanejamento (Rollout)":
            unidades = c1.number_input("Unidades Adicionais", value=5, step=STEP_RESOURCE)
            burn = c2.number_input("Custo Equipe/Mês", value=120000.0, step=STEP_MACRO_MONEY)
            pace = c3.slider("Pace (Un/Mês)", 0.5, 5.0, 1.5)
            impacto_cat_nominal = (unidades / pace) * burn
        
        elif cat_impacto == "Retrabalho (Escopo)":
            hh_total = c1.number_input("H/H Estimada", value=300, step=STEP_RESOURCE)
            custo_hh = c2.number_input("Custo Médio H/H", value=165.0, step=STEP_MONEY)
            impacto_cat_nominal = hh_total * custo_hh
            
        elif cat_impacto == "Instabilidade (Bugs)":
            bugs = c1.number_input("Qtd de Chamados", value=40, step=STEP_RESOURCE)
            tempo_bug = c2.number_input("H/H por Bug", value=12, step=STEP_RESOURCE)
            impacto_cat_nominal = bugs * tempo_bug * 150.0 # Base fixa para Dev
            
        elif cat_impacto == "Infraestrutura (Ociosidade)":
            dias = c1.number_input("Dias de Bloqueio", value=3, step=STEP_RESOURCE)
            daily_cost = c2.number_input("Custo Diário Time", value=15000.0, step=STEP_MACRO_MONEY)
            impacto_cat_nominal = dias * daily_cost

    # 2. ALOCAÇÃO ADICIONAL
    st.subheader("2. Reforço de Staff (Mitigação)")
    with st.expander("➕ Adicionar Recursos ao Cenário", expanded=False):
        with st.form("add_rec"):
            f1, f2, f3 = st.columns([2,1,1])
            func_name = f1.selectbox("Papel", ["Consultor Sr", "Arquiteto", "Dev Fullstack", "PMO Support"])
            c_hora = f2.number_input("Custo/Hora", value=140.0, step=STEP_MONEY)
            qtd_h = f3.number_input("Horas", value=160, step=STEP_RESOURCE)
            if st.form_submit_button("Vincular Recurso"):
                db_conn.execute("INSERT INTO recursos (projeto, funcao, custo_h, horas, subtotal) VALUES (?,?,?,?,?)",
                             (proj, func_name, c_hora, qtd_h, c_hora * qtd_h))
                db_conn.commit()
                st.rerun()

    df_rec = pd.read_sql_query(f"SELECT * FROM recursos WHERE projeto = '{proj}'", db_conn)
    total_recursos = df_rec['subtotal'].sum() if not df_rec.empty else 0.0

    # 3. CONSOLIDAÇÃO FINANCEIRA
    st.divider()
    m_base = impacto_cat_nominal + total_recursos
    
    # Monte Carlo dinâmico
    val_mean, val_p95 = run_monte_carlo(m_base * 0.9, m_base, m_base * 1.5)
    margem_pos = (1 - ((custo_eac_base + val_p95) / receita_net)) * 100 if receita_net > 0 else 0

    col_m1, col_m2, col_m3 = st.columns(3)
    col_m1.metric("Custo Nominal", format_currency(m_base))
    col_m2.metric("Custo P95 (Teto)", format_currency(val_p95), delta="Exposição de Risco")
    col_m3.metric("Margem Final", f"{margem_pos:.2f}%", delta=f"{margem_pos - 25:.2f}% vs Meta", delta_color="inverse")

    # 4. GERAÇÃO DE PDF (FIXED VERSION)
    if st.button("📑 Emitir Parecer Técnico (PDF)"):
        pdf = ExecutivePDF()
        pdf.add_page()
        pdf.set_font("Arial", 'B', 12)
        pdf.cell(0, 10, f"Projeto: {proj}", ln=1)
        pdf.cell(0, 10, f"Categoria de Impacto: {cat_impacto}", ln=1)
        pdf.cell(0, 10, f"Valor P95: {format_currency(val_p95)}", ln=1)
        pdf.cell(0, 10, f"Impacto em Margem: {margem_pos:.2f}%", ln=1)
        
        # A solução definitiva para o erro de output:
        try:
            pdf_bytes = pdf.output() # fpdf2 retorna bytes por padrão
            if isinstance(pdf_bytes, str): # se for fpdf antigo
                pdf_bytes = pdf_bytes.encode('latin-1')
        except:
            pdf_bytes = pdf.output(dest='S').encode('latin-1')
            
        st.download_button("📥 Baixar Relatório", data=pdf_bytes, file_name=f"Parecer_{proj}.pdf", mime="application/pdf")

with t2:
    st.header("Análise de Pareto de Impacto")
    if not df_rec.empty or impacto_cat_nominal > 0:
        data_plot = []
        if impacto_cat_nominal > 0: data_plot.append({'Item': cat_impacto, 'Valor': impacto_cat_nominal})
        for _, r in df_rec.iterrows(): data_plot.append({'Item': r['funcao'], 'Valor': r['subtotal']})
        
        fig = px.bar(pd.DataFrame(data_plot), x='Item', y='Valor', color='Item', title="Distribuição do Custo Adicional")
        st.plotly_chart(fig, use_container_width=True)

with t3:
    st.header("Hub de Cenários Estratégicos")
    nome_cen = st.text_input("Nome do Snapshot (ex: Mitigação com Time Externo)")
    if st.button("💾 Salvar para Decisão"):
        db_conn.execute("INSERT INTO cenarios (projeto, nome_cenario, impacto_p95, margem, data) VALUES (?,?,?,?,?)",
                     (proj, nome_cen, val_p95, margem_pos, datetime.now().strftime("%d/%m %H:%M")))
        db_conn.commit()
    
    df_h = pd.read_sql_query(f"SELECT * FROM cenarios WHERE projeto = '{proj}'", db_conn)
    st.dataframe(df_h[['nome_cenario', 'impacto_p95', 'margem', 'data']], use_container_width=True)
