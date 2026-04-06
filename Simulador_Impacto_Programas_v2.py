import streamlit as st
import matplotlib.pyplot as plt
import pandas as pd
import sqlite3
import numpy as np
import plotly.graph_objects as go
import plotly.express as px
from fpdf import FPDF
from datetime import datetime, timedelta
import tempfile
import os
import json

# --- CONFIGURAÇÕES DE INTERFACE ---
def local_css():
    st.markdown("""
    <style>
        .main { background-color: #f8f9fa; }
        .stMetric { background-color: white; padding: 15px; border-radius: 8px; border-top: 4px solid #003366; box-shadow: 0 2px 4px rgba(0,0,0,0.05); }
        .header-box { background-color: white; padding: 20px; border-radius: 10px; border-left: 10px solid #003366; margin-bottom: 20px; box-shadow: 0 4px 12px rgba(0,0,0,0.1); }
        .section-header { color: #003366; font-weight: bold; margin-top: 30px; border-bottom: 2px solid #e0e0e0; padding-bottom: 5px; font-size: 1.2rem; }
    </style>
    """, unsafe_allow_html=True)

# --- ENGINE DE DADOS ---
def init_db():
    conn = sqlite3.connect('pmo_elite_v2.db', check_same_thread=False)
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS matriz_alocacao 
                 (id INTEGER PRIMARY KEY AUTOINCREMENT, projeto TEXT, cargo TEXT, nivel TEXT, 
                  reg TEXT, taxa REAL, horas_json TEXT, total REAL)''')
    c.execute('''CREATE TABLE IF NOT EXISTS resumo_impacto 
                 (id INTEGER PRIMARY KEY AUTOINCREMENT, data_geracao TEXT, projeto TEXT, 
                  custo_total REAL, margem_antes REAL, margem_depois REAL, erosao REAL)''')
    conn.commit()
    return conn

db_conn = init_db()

# --- CLASSE PDF PROFISSIONAL ---
class RelatorioExecutivo(FPDF):
    def header(self):
        self.set_font('Arial', 'B', 14)
        self.set_text_color(0, 51, 102)
        self.cell(0, 10, 'DOSSIE DE IMPACTO FINANCEIRO E EROSAO DE MARGEM', 0, 1, 'C')
        self.set_font('Arial', 'I', 9)
        self.cell(0, 5, 'PMO CORPORATIVO - DIRETORIA DE OPERACOES', 0, 1, 'C')
        self.ln(5)
        self.set_draw_color(0, 51, 102)
        self.set_line_width(0.8)
        self.line(10, 28, 200, 28)
        self.ln(10)

    def footer(self):
        self.set_y(-15)
        self.set_font('Arial', 'I', 7)
        self.cell(0, 10, f'Pagina {self.page_no()} | CONFIDENCIAL | Gerado em {datetime.now().strftime("%d/%m/%Y %H:%M")}', 0, 0, 'C')

    def assinaturas(self):
        self.set_y(-50)
        self.set_font('Arial', 'B', 8)
        self.set_draw_color(150, 150, 150)
        self.line(20, self.get_y(), 90, self.get_y())
        self.line(120, self.get_y(), 190, self.get_y())
        self.cell(95, 8, 'Diretoria de Operacoes', 0, 0, 'C')
        self.cell(95, 8, 'Gerencia do Programa', 0, 1, 'C')

    def chapter_title(self, label):
        self.set_font('Arial', 'B', 11)
        self.set_fill_color(230, 230, 230)
        self.set_text_color(0, 51, 102)
        self.cell(0, 8, f" {label}", 0, 1, 'L', fill=True)
        self.ln(3)

# --- FUNÇÕES DE SUPORTE ---
def format_brl(val):
    return f"R$ {val:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")

def metric_card_custom(label, value, delta_val):
    is_negative = delta_val > 0 
    color = "#d32f2f" if is_negative else "#2e7d32"
    bg_color = "#ffeeee" if is_negative else "#e8f5e9"
    arrow = "↓" if is_negative else "↑"
    st.markdown(f"""
    <div style="background-color: white; padding: 15px; border-radius: 8px; border-top: 4px solid {color}; box-shadow: 0 2px 4px rgba(0,0,0,0.05); text-align: left;">
        <p style="color: #666; font-size: 14px; margin: 0;">{label}</p>
        <h2 style="margin: 5px 0; color: #333;">{value}</h2>
        <div style="background-color: {bg_color}; color: {color}; padding: 2px 8px; border-radius: 4px; display: inline-block; font-weight: bold; font-size: 14px;">
            {arrow} {delta_val:.2f}%
        </div>
    </div>
    """, unsafe_allow_html=True)

def get_meses_list(start_date, months):
    return [(start_date.replace(day=1) + timedelta(days=31*i)).strftime("%b/%y").upper() for i in range(months)]

# --- INTERFACE ---
st.set_page_config(page_title="Simulador de Impacto Financeiro", layout="wide")
local_css()

LISTA_PROGRAMAS = [" ", "INS", "EINSTEIN", "CEMA", "MOGI", "RHP", "HCM", "HCS", "SoulBene Digital", "Girassol", "Bauru"]
LISTA_GERENTES = [" ", "Mariane Mylius", "Rosemary Lopes", "Lizia Cunha", "Sergio Carvalho", "Roberio Matos ", "Kamyla Ferrarezi", "Cristiano Gomes", "Ana Alencar", "Marcela Prates", "Luiza Liberal", "Jose Alexandre" ]

st.markdown('<div class="header-box"><h2 style="margin:0; color:#003366;">📑 Análise de Impacto Financeiro - PMO PROGRAMAS</h2></div>', unsafe_allow_html=True)

# 1. INFORMAÇÕES
with st.container(border=True):
    c1, c2 = st.columns(2)
    prog_nome = c1.selectbox("Programa", options=LISTA_PROGRAMAS, key="sel_prog")
    prog_gerente = c2.selectbox("Gerente do Programa", options=LISTA_GERENTES, key="sel_gerente")
    contexto = st.text_area("Contexto da Mudança", placeholder="Motivo do impacto...")

# 3. MATRIZ DE ALOCAÇÃO
st.markdown('<div class="section-header">3. Matriz de Alocação e Orçamento</div>', unsafe_allow_html=True)
with st.container(border=True):
    m1, m2 = st.columns(2)
    data_inicio = m1.date_input("Início do Impacto", value=datetime.now())
    horizonte = m2.number_input("Meses (Horizonte)", min_value=1, value=1)
    lista_meses = get_meses_list(data_inicio, horizonte)

    with st.expander("➕ Adicionar Recurso"):
        f1, f2, f3 = st.columns(3)
        cargo = f1.selectbox("Cargo", ["Analista", "Consultor", "Especialista", "Gerente"])
        nivel = f2.selectbox("Nível", ["Junior", "Pleno", "Senior"])
        reg_cc = f3.text_input("Regional", "Sede")
        taxa_h = st.number_input("Taxa/Hora (R$)", value=150.0)
        if st.button("ADICIONAR RECURSO"):
            h_dist = {m: 160.0 for m in lista_meses}
            db_conn.execute("INSERT INTO matriz_alocacao (projeto, cargo, nivel, reg, taxa, horas_json, total) VALUES (?,?,?,?,?,?,?)",
                         (prog_nome, cargo, nivel, reg_cc, taxa_h, json.dumps(h_dist), 0.0))
            db_conn.commit()
            st.rerun()

    df_raw = pd.read_sql_query(f"SELECT * FROM matriz_alocacao WHERE projeto='{prog_nome}'", db_conn)
    if not df_raw.empty:
        df_edit = df_raw.copy()
        for mes in lista_meses:
            df_edit[mes] = df_edit['horas_json'].apply(lambda x: json.loads(x).get(mes, 0.0))
        
        edited_df = st.data_editor(df_edit.drop(columns=['horas_json']), num_rows="dynamic", use_container_width=True, key="editor")
        custo_base_total = (edited_df[lista_meses].sum(axis=1) * edited_df['taxa']).sum()
    else:
        custo_base_total = 0.0

# 4. DRE E MARGEM
total_cenario = custo_base_total * 1.15
receita_liq = st.number_input("Receita Líquida Atual", value=1000.0)
custo_atual = st.number_input("Custo Atual (EAC)", value=500.0)

margem_atual = (1 - (custo_atual/receita_liq)) * 100
margem_final = (1 - ((custo_atual + total_cenario)/receita_liq)) * 100
erosao = margem_atual - margem_final

st.divider()
r1, r2, r3 = st.columns(3)
r1.metric("Margem Atual", f"{margem_atual:.2f}%")
with r2: metric_card_custom("Margem Projetada", f"{margem_final:.2f}%", erosao)
r3.metric("Erosão", f"{erosao:.2f} p.p.")

# --- BOTÃO SALVAR E PDF ---
if st.sidebar.button("💾 SALVAR E GERAR PDF"):
    pdf = RelatorioExecutivo()
    pdf.add_page()
    pdf.chapter_title("1. IDENTIFICACAO DO PROGRAMA")
    pdf.set_font('Arial', '', 10)
    pdf.cell(0, 10, f"Programa: {prog_nome} | Gerente: {prog_gerente}", 0, 1)
    
    # Gráficos
    try:
        fig_hist, ax = plt.subplots(figsize=(5, 3))
        ax.bar(['Baseline', 'Impacto'], [margem_atual, margem_final], color=['#003366', '#d32f2f'])
        with tempfile.NamedTemporaryFile(delete=False, suffix=".png") as tmp:
            plt.savefig(tmp.name, format='png', bbox_inches='tight')
            pdf.image(tmp.name, x=15, y=pdf.get_y() + 10, w=80)
        plt.close(fig_hist)
    except Exception as e:
        st.error(f"Erro gráfico: {e}")

    pdf.assinaturas()
    output = pdf.output(dest='S')
    st.sidebar.download_button("📥 Baixar PDF", data=bytes(output), file_name=f"Dossie_{prog_nome}.pdf", mime="application/pdf")
