import streamlit as st
import pandas as pd
import sqlite3
import numpy as np
import plotly.graph_objects as go
import matplotlib.pyplot as plt
import seaborn as sns
from fpdf import FPDF
from datetime import datetime
from PIL import Image
import io
import os

# --- CONFIGURAÇÕES DE ESCALA (CONFORME SOLICITADO) ---
STEP_MONEY = 10.0
STEP_MACRO_MONEY = 1000.0
STEP_RESOURCE = 1

# --- CONFIGURAÇÃO DA PÁGINA ---
st.set_page_config(page_title="MV PMO Decision Intelligence", layout="wide")

# --- ESTILO CSS ---
st.markdown("""
    <style>
    .main { background-color: #f4f7f9; }
    .stMetric { background-color: #ffffff; border-left: 5px solid #003366; padding: 15px; border-radius: 5px; }
    div.stButton > button:first-child { background-color: #003366; color: white; width: 100%; border-radius: 5px; }
    </style>
    """, unsafe_allow_html=True)

# --- FUNÇÕES CORE ---
def format_currency(val):
    return f"R$ {val:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")

def calc_pert(o, m, p):
    return (o + 4*m + p) / 6

def run_monte_carlo(o, m, p, n=5000):
    if o >= p: return m, m
    sims = np.random.triangular(o, m, p, n)
    return np.mean(sims), np.percentile(sims, 95)

# --- DATABASE ---
def init_db():
    conn = sqlite3.connect('pmo_master.db', check_same_thread=False)
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS recursos (id INTEGER PRIMARY KEY AUTOINCREMENT, 
                 projeto TEXT, funcao TEXT, senioridade TEXT, custo_h REAL, horas INTEGER, subtotal REAL)''')
    conn.commit()
    return conn

db_conn = init_db()

# --- CLASSE PDF EXECUTIVO ---
class ExecutivePDF(FPDF):
    def header(self):
        try:
            self.image("Logomarca MV Atualizada.png", 10, 8, 25)
        except: pass
        self.set_font('Arial', 'B', 15)
        self.set_text_color(0, 51, 102)
        self.cell(0, 10, 'PARECER TECNICO DE IMPACTO ECONOMICO', 0, 1, 'R')
        self.set_font('Arial', '', 9)
        self.cell(0, 5, f'Emitido em: {datetime.now().strftime("%d/%m/%Y %H:%M")}', 0, 1, 'R')
        self.ln(15)
        # Watermark
        self.set_font('Arial', 'B', 40)
        self.set_text_color(240, 240, 240)
        with self.rotation(45, 100, 150):
            self.text(40, 190, "CONFIDENTIAL")

    def footer(self):
        self.set_y(-30)
        self.set_font('Arial', 'B', 8)
        self.set_text_color(100)
        self.cell(0, 10, 'Desenvolvido por PMO Corporativo de Programas', 0, 0, 'C')
        self.set_y(-20)
        self.line(30, self.get_y(), 80, self.get_y())
        self.line(130, self.get_y(), 180, self.get_y())
        self.set_font('Arial', '', 7)
        self.text(40, self.get_y()+4, "GERENTE DO PROGRAMA")
        self.text(140, self.get_y()+4, "DIRETOR DE OPERAÇÕES")

# --- SIDEBAR: DADOS MESTRES ---
with st.sidebar:
    try:
        st.image("Logomarca MV Atualizada.png", width=120)
    except: pass
    st.title("⚙️ Configuração Master")
    proj = st.selectbox("Programa", ["UNIMED SERRA GAUCHA", "INS", "CLINICA GIRASSOL", "EINSTEIN", "MOGI", "RHP"])
    gerente = st.text_input("Gerente Responsável", "Kamyla")
    receita_net = st.number_input("Receita Líquida (R$)", value=4719147.0, step=STEP_MACRO_MONEY)
    custo_eac = st.number_input("Custo Atual EAC (R$)", value=4963246.0, step=STEP_MACRO_MONEY)

# --- CABEÇALHO ---
st.title("🛡️ MV PMO Decision Intelligence")
st.markdown(f"**Análise de Impacto: {proj}**")

# --- 1. CATEGORIAS DE IMPACTO (HIDE AND SHOW) ---
st.subheader("1. Escopo e Justificativa")
cat_selecionada = st.selectbox("Categoria Principal do Impacto", 
                              [" ", "Replanejamento (Rollout)", "Retrabalho (Escopo)", "Instabilidade (Bugs)", "Infraestrutura (Ociosidade)"])

impacto_auto_base = 0.0
if cat_selecionada != " ":
    with st.expander(f"Configuração Detalhada: {cat_selecionada}", expanded=True):
        col_c1, col_c2, col_c3 = st.columns(3)
        if cat_selecionada == "Replanejamento (Rollout)":
            v1 = col_c1.number_input("Rollouts Restantes", value=11, step=STEP_RESOURCE)
            v2 = col_c2.number_input("Burn Mensal Equipe (R$)", value=250000.0, step=STEP_MACRO_MONEY)
            v3 = col_c3.slider("Novo Pace Estimado (un/mês)", 1.0, 10.0, 5.0)
            impacto_auto_base = (v1 / v3) * v2
        elif cat_selecionada == "Retrabalho (Escopo)":
            v1 = col_c1.number_input("Qtd Itens Retrabalho", value=5, step=STEP_RESOURCE)
            v2 = col_c2.number_input("H/H Média por Item", value=40.0, step=1.0)
            v3 = col_c3.number_input("Custo Médio Hora (R$)", value=150.0, step=STEP_MONEY)
            impacto_auto_base = v1 * v2 * v3
        else:
            impacto_auto_base = st.number_input("Valor Estimado de Impacto Direto (R$)", value=0.0, step=STEP_MACRO_MONEY)

# --- 2. ALOCAÇÃO DE RECURSOS (HIDE AND SHOW) ---
st.subheader("2. Gestão de Alocação (Custo Variável)")
with st.expander("➕ Adicionar/Ajustar Recursos Humanos", expanded=False):
    with st.form("form_rec"):
        f1, f2, f3, f4 = st.columns([2,1,1,1])
        func = f1.selectbox("Função", ["Consultor", "Analista", "Arquiteto", "Dev", "PMO"])
        seni = f2.selectbox("Nível", ["Jr", "Pl", "Sr", "Esp"])
        ch = f3.number_input("Custo/Hora", value=130.0, step=STEP_MONEY)
        hr = f4.number_input("Qtd Horas", value=160, step=STEP_RESOURCE)
        if st.form_submit_button("Confirmar Alocação"):
            db_conn.execute("INSERT INTO recursos (projeto, funcao, senioridade, custo_h, horas, subtotal) VALUES (?,?,?,?,?,?)",
                         (proj, func, seni, ch, hr, ch*hr))
            db_conn.commit()
            st.rerun()

df_rec = pd.read_sql_query(f"SELECT * FROM recursos WHERE projeto = '{proj}'", db_conn)
custo_alocacao = df_rec['subtotal'].sum() if not df_rec.empty else 0.0

if not df_rec.empty:
    st.dataframe(df_rec[['funcao', 'senioridade', 'custo_h', 'horas', 'subtotal']], use_container_width=True)
    if st.button("🗑️ Resetar Alocação"):
        db_conn.execute(f"DELETE FROM recursos WHERE projeto = '{proj}'")
        db_conn.commit()
        st.rerun()

# --- 3. MODELAGEM PERT & MONTE CARLO ---
st.divider()
total_impacto_nominal = impacto_auto_base + custo_alocacao

st.subheader("3. Modelagem de Risco e Incerteza")
col_p1, col_p2 = st.columns([1, 2])

with col_p1:
    o = st.number_input("Cenário Otimista (R$)", value=total_impacto_nominal * 0.9, step=STEP_MACRO_MONEY)
    m = total_impacto_nominal
    p = st.number_input("Cenário Pessimista (R$)", value=total_impacto_nominal * 1.6, step=STEP_MACRO_MONEY)
    
    val_pert = calc_pert(o, m, p)
    _, val_mc = run_monte_carlo(o, m, p)
    delta_risk = val_mc - m

with col_p2:
    st.write("**Exposição Financeira Estimada**")
    c_m1, c_m2, c_m3 = st.columns(3)
    c_m1.metric("Impacto Nominal", format_currency(m))
    c_m2.metric("PERT (Provável)", format_currency(val_pert))
    c_m3.metric("P95 (Teto Risco)", format_currency(val_mc), delta=format_currency(delta_risk), delta_color="inverse")

# --- 4. DRE E TRIÂNGULO DE FERRO ---
st.divider()
st.subheader("4. Visão Executiva: Margem e Triângulo de Ferro")

col_d1, col_d2 = st.columns([1.5, 1])

with col_d1:
    # Cálculo de Margens
    eac_final = custo_eac + val_mc
    margem_original = (1 - (custo_eac / receita_net)) * 100 if receita_net > 0 else 0
    margem_projetada = (1 - (eac_final / receita_net)) * 100 if receita_net > 0 else 0
    
    st.write("**Análise de Erosão de Margem**")
    fig_bar = go.Figure()
    fig_bar.add_trace(go.Bar(name='Margem Original', x=[proj], y=[margem_original], marker_color='#003366'))
    fig_bar.add_trace(go.Bar(name='Margem Pós-Impacto (P95)', x=[proj], y=[margem_projetada], marker_color='#C0392B'))
    fig_bar.update_layout(height=300, yaxis_title="Margem (%)")
    st.plotly_chart(fig_bar, use_container_width=True)

with col_d2:
    # Triângulo de Ferro (Normalizado 0 a 2, onde 1 é o equilíbrio)
    st.write("**Impacto no Triângulo de Ferro**")
    cost_v = val_mc / (m * 1.2) if m > 0 else 1.0
    time_v = 1.4 if "Replanejamento" in cat_selecionada else 1.1
    scope_v = 1.5 if "Retrabalho" in cat_selecionada else 1.1
    
    fig_radar = go.Figure()
    fig_radar.add_trace(go.Scatterpolar(r=[1,1,1,1], theta=['Custo','Prazo','Escopo','Custo'], fill='toself', name='Baseline'))
    fig_radar.add_trace(go.Scatterpolar(r=[cost_v, time_v, scope_v, cost_v], theta=['Custo','Prazo','Escopo','Custo'], fill='toself', name='Cenário Atual', line_color='red'))
    fig_radar.update_layout(polar=dict(radialaxis=dict(visible=True, range=[0, 2])), height=300, margin=dict(t=20, b=20, l=40, r=40))
    st.plotly_chart(fig_radar, use_container_width=True)

# --- 5. GERAÇÃO DE RELATÓRIO ---
st.divider()
if st.button("📑 GERAR RELATÓRIO EXECUTIVO PARA VALIDAÇÃO"):
    pdf = ExecutivePDF()
    pdf.add_page()
    pdf.set_font("Arial", 'B', 12)
    pdf.cell(0, 10, f"Projeto: {proj}", ln=1)
    pdf.set_font("Arial", '', 11)
    pdf.cell(0, 10, f"Gerente: {gerente} | Categoria: {cat_selecionada}", ln=1)
    
    pdf.ln(5)
    pdf.set_fill_color(0, 51, 102); pdf.set_text_color(255)
    pdf.cell(0, 8, " RESUMO FINANCEIRO E RISCO", ln=1, fill=True)
    pdf.set_text_color(0)
    pdf.cell(95, 10, f"Receita Liquida: {format_currency(receita_net)}", border=1)
    pdf.cell(95, 10, f"Custo EAC Base: {format_currency(custo_eac)}", border=1, ln=1)
    pdf.cell(95, 10, f"Impacto P95 (Teto): {format_currency(val_mc)}", border=1)
    pdf.cell(95, 10, f"Margem Final: {margem_projetada:.2f}%", border=1, ln=1)
    
    if not df_rec.empty:
        pdf.ln(5)
        pdf.set_fill_color(200, 200, 200); pdf.set_text_color(0)
        pdf.cell(0, 8, " DETALHAMENTO DE RECURSOS ALOCADOS", ln=1, fill=True)
        pdf.set_font("Arial", 'B', 9)
        pdf.cell(60, 8, "Função", 1); pdf.cell(40, 8, "Nível", 1); pdf.cell(30, 8, "Horas", 1); pdf.cell(60, 8, "Subtotal", 1, ln=1)
        pdf.set_font("Arial", '', 9)
        for _, r in df_rec.iterrows():
            pdf.cell(60, 8, r['funcao'], 1); pdf.cell(40, 8, r['senioridade'], 1); pdf.cell(30, 8, str(r['horas']), 1); pdf.cell(60, 8, format_currency(r['subtotal']), 1, ln=1)

    pdf_bytes = pdf.output(dest='S').encode('latin-1', 'replace')
    st.download_button(label="📥 Baixar Relatório A4 (Confidential)", data=pdf_bytes, file_name=f"PARECER_{proj}.pdf", mime="application/pdf")
