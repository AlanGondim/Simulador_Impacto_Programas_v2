import streamlit as st
import pandas as pd
import sqlite3
import numpy as np
import plotly.graph_objects as go
import plotly.express as px
from fpdf import FPDF
from datetime import datetime
from dateutil.relativedelta import relativedelta
import tempfile
import os

# --- CONFIGURAÇÕES DE ESTILO ---
def local_css():
    st.markdown("""
    <style>
        .main { background-color: #f8f9fa; }
        .stMetric { background-color: white; padding: 15px; border-radius: 10px; border-top: 4px solid #003366; box-shadow: 2px 2px 5px rgba(0,0,0,0.05); }
        .header-box { background-color: white; padding: 20px; border-radius: 10px; border-left: 10px solid #003366; margin-bottom: 20px; }
        .section-header { color: #003366; font-weight: bold; border-bottom: 2px solid #00bfa5; margin-bottom: 15px; padding-bottom: 5px; font-size: 1.3rem; }
    </style>
    """, unsafe_allow_html=True)

# --- DATABASE ---
def init_db():
    conn = sqlite3.connect('pmo_enterprise_v3.db', check_same_thread=False)
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS matriz_alocacao 
                 (id INTEGER PRIMARY KEY AUTOINCREMENT, projeto TEXT, cargo TEXT, nivel TEXT, 
                  taxa REAL, horas_json TEXT, total REAL)''')
    conn.commit()
    return conn

db_conn = init_db()

# --- CLASSE PDF EXECUTIVO ---
class PDF_Relatorio(FPDF):
    def header(self):
        self.set_font('Arial', 'B', 12)
        self.set_text_color(0, 51, 102)
        self.cell(0, 10, 'RELATORIO DE IMPACTO FINANCEIRO - PMO ENTERPRISE', 0, 1, 'R')
        self.line(10, 25, 200, 25)
        self.ln(10)

    def footer(self):
        self.set_y(-15)
        self.set_font('Arial', 'I', 8)
        self.set_text_color(150)
        self.cell(0, 10, f'Pagina {self.page_no()} | CONFIDENCIAL - DIRETORIA DE OPERACOES', 0, 0, 'C')

    def draw_watermark(self):
        self.set_font('Arial', 'B', 50)
        self.set_text_color(240, 240, 240)
        self.rotate(45, 100, 150)
        self.text(40, 190, 'CONFIDENCIAL')
        self.rotate(0)

# --- FUNÇÕES DE CÁLCULO ---
def format_currency(val):
    return f"R$ {val:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")

def get_month_list(start_date, count):
    months = []
    for i in range(count):
        # Correção: relativedelta garante que não pule meses como Fevereiro
        m = start_date + relativedelta(months=i)
        months.append(m.strftime("%b/%y").lower())
    return months

# --- UI STREAMLIT ---
st.set_page_config(page_title="PMO Intelligence Pro", layout="wide")
local_css()

# Cabeçalho
st.markdown('<div class="header-box"><h1>📋 Gestão de Impacto e Erosão de Margem</h1><p>Diretoria de Operações | Relatório de Governança</p></div>', unsafe_allow_html=True)

# 1. SETUP DO PROGRAMA
st.markdown('<div class="section-header">1. Informações Estratégicas</div>', unsafe_allow_html=True)
col_a, col_b, col_c = st.columns([2, 1, 1])
nome_proj = col_a.text_input("NOME DO PROGRAMA / PROJETO", value="Einstein - Rollout ACS")
data_impacto = col_b.date_input("INÍCIO DO IMPACTO", value=datetime(2026, 3, 1))
meses_horizonte = col_c.number_input("MESES (HORIZONTE)", min_value=1, max_value=12, value=4)

lista_meses_label = get_month_list(data_impacto, meses_horizonte)

# 2. MATRIZ DE ALOCAÇÃO & ORÇAMENTO
st.markdown('<div class="section-header">2. Matriz de Alocação e Orçamento (Cenário)</div>', unsafe_allow_html=True)
with st.container(border=True):
    f1, f2, f3 = st.columns([2, 1, 1])
    cargo_input = f1.selectbox("Função/Cargo", ["Consultor Senior", "Analista Pleno", "Gerente de Projetos", "Arquiteto de Soluções"])
    taxa_input = f2.number_input("Taxa/Hora (R$)", value=185.0)
    
    st.write("Distribuição de Horas Mensais:")
    h_cols = st.columns(meses_horizonte)
    horas_dict = {}
    for idx, mes_lab in enumerate(lista_meses_label):
        horas_dict[mes_lab] = h_cols[idx].number_input(f"{mes_lab}", value=160, key=f"h_{idx}")

    if st.button("➕ Adicionar Recurso à Matriz"):
        total_res = sum(horas_dict.values()) * taxa_input
        db_conn.execute("INSERT INTO matriz_alocacao (projeto, cargo, nivel, taxa, horas_json, total) VALUES (?,?,?,?,?,?)",
                     (nome_proj, cargo_input, "Nível III", taxa_input, str(horas_dict), total_res))
        db_conn.commit()
        st.success("Recurso alocado!")
        st.rerun()

# Exibição da Matriz (Conforme padrão do Print)
df_matriz = pd.read_sql_query(f"SELECT * FROM matriz_alocacao WHERE projeto='{nome_proj}'", db_conn)
if not df_matriz.empty:
    st.dataframe(df_matriz[['cargo', 'taxa', 'total']], use_container_width=True)
    custo_baseline = df_matriz['total'].sum()
else:
    custo_baseline = 0.0

# 3. ANÁLISE INTEGRADA (TRIÂNGULO E HISTOGRAMA)
st.markdown('<div class="section-header">3. Análise Integrada e Triângulo de Ferro</div>', unsafe_allow_html=True)

reserva_risco = custo_baseline * 0.15 # Adicional de 15% para cenário P95
orcamento_total_cenario = custo_baseline + reserva_risco

col_g1, col_g2 = st.columns(2)

with col_g1:
    # Radar Chart - Triângulo de Ferro
    fig_radar = go.Figure()
    fig_radar.add_trace(go.Scatterpolar(r=[1, 1, 1, 1], theta=['Custo','Prazo','Escopo','Custo'], fill='toself', name='Baseline'))
    fig_radar.add_trace(go.Scatterpolar(r=[1.5, 1.3, 1.1, 1.5], theta=['Custo','Prazo','Escopo','Custo'], fill='toself', name='Com Impacto'))
    fig_radar.update_layout(polar=dict(radialaxis=dict(visible=False)), showlegend=True, title="Desvio do Triângulo de Ferro")
    st.plotly_chart(fig_radar, use_container_width=True)

with col_g2:
    # Histograma de Erosão (Correção color_discrete_map)
    df_erosao = pd.DataFrame({
        'Categoria': ['Baseline', 'Risco Adicional', 'Custo Total'],
        'Valor': [custo_baseline, reserva_risco, orcamento_total_cenario]
    })
    fig_hist = px.bar(df_erosao, x='Categoria', y='Valor', color='Categoria',
                     title="Histograma de Erosão de Custos",
                     color_discrete_map={
                         'Baseline': '#003366',
                         'Risco Adicional': '#ff9800',
                         'Custo Total': '#d32f2f'
                     })
    st.plotly_chart(fig_hist, use_container_width=True)

# 4. DRE DO PROGRAMA
st.markdown('<div class="section-header">4. DRE do Programa: Análise de Margem</div>', unsafe_allow_html=True)
receita_total = st.number_input("Receita Bruta do Contrato (R$)", value=5000000.0)
margem_original = 35.0 # Meta

custo_anterior = receita_total * (1 - (margem_original/100))
novo_custo_total = custo_anterior + orcamento_total_cenario
nova_margem = (1 - (novo_custo_total / receita_total)) * 100

c1, c2, c3 = st.columns(3)
c1.metric("Impacto Mensal Margem", f"-{((margem_original - nova_margem)/meses_horizonte):.2f}%")
c2.metric("Margem Final Projetada", f"{nova_margem:.2f}%", delta=f"{nova_margem - margem_original:.1f}%")
c3.metric("Orçamento Total Cenário", format_currency(orcamento_total_cenario))

# 5. EXPORTAÇÃO PDF
if st.button("📑 Gerar Relatório PDF (Validação Diretoria)"):
    pdf = PDF_Relatorio()
    pdf.add_page()
    pdf.draw_watermark()
    
    # Conteúdo PDF
    pdf.set_font('Arial', 'B', 14)
    pdf.cell(0, 10, f"Dossie de Impacto: {nome_proj}", 0, 1)
    
    pdf.set_font('Arial', '', 10)
    pdf.ln(5)
    pdf.cell(0, 8, f"Data da Analise: {datetime.now().strftime('%d/%m/%Y')}", 0, 1)
    pdf.cell(0, 8, f"Orcamento Total Estimado: {format_currency(orcamento_total_cenario)}", 0, 1)
    pdf.cell(0, 8, f"Erosao de Margem: {margem_original - nova_margem:.2f} pontos percentuais", 0, 1)
    
    # Salvar e Inserir Gráficos
    with tempfile.NamedTemporaryFile(delete=False, suffix=".png") as tmp_radar:
        fig_radar.write_image(tmp_radar.name)
        pdf.image(tmp_radar.name, x=10, y=70, w=90)
        
    with tempfile.NamedTemporaryFile(delete=False, suffix=".png") as tmp_hist:
        fig_hist.write_image(tmp_hist.name)
        pdf.image(tmp_hist.name, x=110, y=70, w=90)
    
    # Tabela de DRE no PDF
    pdf.set_y(150)
    pdf.set_fill_color(0, 51, 102)
    pdf.set_text_color(255, 255, 255)
    pdf.cell(90, 10, "Indicador", 1, 0, 'C', True)
    pdf.cell(90, 10, "Valor Projetado", 1, 1, 'C', True)
    
    pdf.set_text_color(0, 0, 0)
    pdf.cell(90, 10, "Receita de Contrato", 1); pdf.cell(90, 10, format_currency(receita_total), 1, 1)
    pdf.cell(90, 10, "Custo Total (Base + Impacto)", 1); pdf.cell(90, 10, format_currency(novo_custo_total), 1, 1)
    pdf.cell(90, 10, "Margem Final", 1); pdf.cell(90, 10, f"{nova_margem:.2f}%", 1, 1)

    # Output
    pdf_bytes = pdf.output(dest='S')
    st.download_button(label="📥 Baixar Dossiê Completo (PDF)", data=bytes(pdf_bytes), file_name=f"Relatorio_PMO_{nome_proj}.pdf", mime="application/pdf")
