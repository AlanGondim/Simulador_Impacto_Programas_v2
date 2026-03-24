import streamlit as st
import pandas as pd
import sqlite3
import numpy as np
import plotly.graph_objects as go
from fpdf import FPDF
from datetime import datetime
import os

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

def calc_pert(o, m, p):
    return (o + 4*m + p) / 6

def run_monte_carlo(o, m, p, n=5000):
    if o >= p: return m, m
    sims = np.random.triangular(o, m, p, n)
    return np.mean(sims), np.percentile(sims, 95)

# --- CLASSE PDF CORRIGIDA ---
class ExecutivePDF(FPDF):
    def header(self):
        self.set_font('Arial', 'B', 15)
        self.set_text_color(0, 51, 102)
        self.cell(0, 10, 'PARECER TECNICO DE IMPACTO ECONOMICO', 0, 1, 'R')
        self.ln(10)

    def footer(self):
        self.set_y(-15)
        self.set_font('Arial', 'I', 8)
        self.cell(0, 10, f'Pagina {self.page_no()}', 0, 0, 'C')

# --- INTERFACE ---
st.title("🛡️ MV PMO Decision Intelligence")

with st.sidebar:
    st.title("⚙️ Configuração Master")
    proj = st.selectbox("Programa", ["UNIMED SERRA GAUCHA", "INS", "CLINICA GIRASSOL", "EINSTEIN", "RHP"])
    receita_net = st.number_input("Receita Líquida (R$)", value=4719147.0, step=STEP_MACRO_MONEY)
    custo_eac_base = st.number_input("Custo Atual EAC (R$)", value=4963246.0, step=STEP_MACRO_MONEY)

tab1, tab2 = st.tabs(["🚀 Simulação Ativa", "📚 Hub de Cenários"])

with tab1:
    # 1. Alocação de Recursos (Hide/Show)
    with st.expander("👥 Gestão de Alocação de Recursos", expanded=False):
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
            st.table(df_rec[['funcao', 'custo_h', 'horas', 'subtotal']])
            if st.button("🗑️ Resetar Alocação"):
                db_conn.execute(f"DELETE FROM recursos WHERE projeto = '{proj}'")
                db_conn.commit()
                st.rerun()

    # 2. Modelagem Estatística
    custo_nominal = df_rec['subtotal'].sum() if not df_rec.empty else 0.0
    st.subheader("🎲 Modelagem de Risco")
    c1, c2, c3 = st.columns(3)
    o = c1.number_input("Otimista", value=custo_nominal * 0.9, step=STEP_MONEY)
    m = custo_nominal
    p = c2.number_input("Pessimista", value=custo_nominal * 1.5, step=STEP_MONEY)
    
    val_pert, val_p95 = run_monte_carlo(o, m, p)
    c3.metric("Teto de Risco (P95)", format_currency(val_p95))

    # 3. Triângulo de Ferro Interativo
    st.divider()
    col_radar, col_save = st.columns([2, 1])
    
    with col_radar:
        st.write("**Triângulo de Ferro (Impacto Projetado)**")
        cost_v = val_p95 / (m * 1.2) if m > 0 else 1.0
        fig_radar = go.Figure()
        fig_radar.add_trace(go.Scatterpolar(r=[1,1,1,1], theta=['Custo','Prazo','Escopo','Custo'], fill='toself', name='Base'))
        fig_radar.add_trace(go.Scatterpolar(r=[cost_v, 1.2, 1.1, cost_v], theta=['Custo','Prazo','Escopo','Custo'], fill='toself', name='Impacto', line_color='red'))
        fig_radar.update_layout(polar=dict(radialaxis=dict(visible=True, range=[0, 2])), height=350)
        st.plotly_chart(fig_radar)

    with col_save:
        st.write("**Protocolar Cenário**")
        nome_cen = st.text_input("Nome do Cenário", "Plano de Mitigação A")
        margem_final = (1 - ((custo_eac_base + val_p95) / receita_net)) *
