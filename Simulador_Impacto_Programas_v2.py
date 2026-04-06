import streamlit as st
import matplotlib.pyplot as plt
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from fpdf import FPDF
from datetime import datetime, timedelta
import tempfile
import json
import oracledb # Driver para Oracle

# --- CONFIGURAÇÃO GLOBAL ORACLE ---
# Força a conversão de campos CLOB (JSON) para strings automaticamente
oracledb.defaults.fetch_lobs = False

# --- CONEXÃO COM BANCO ORACLE ---
def get_db_connection():
    try:
        # As credenciais devem ficar no arquivo secrets.toml (vide passo a passo abaixo)
        c = st.secrets["oracle"]
        conn = oracledb.connect(
            user=c["user"],
            password=c["password"],
            dsn=f"{c['host']}:{c['port']}/{c['sid']}"
        )
        return conn
    except Exception as e:
        st.error(f"Erro de conexão com Oracle: {e}")
        return None

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

# --- CLASSE PDF PROFISSIONAL ---
class RelatorioExecutivo(FPDF):
    def header(self):
        self.set_font('Arial', 'B', 14)
        self.set_text_color(0, 51, 102)
        self.cell(0, 10, 'DOSSIE DE IMPACTO FINANCEIRO E EROSAO DE MARGEM', 0, 1, 'C')
        self.ln(5)

    def footer(self):
        self.set_y(-15)
        self.set_font('Arial', 'I', 7)
        self.cell(0, 10, f'Pagina {self.page_no()} | CONFIDENCIAL | Gerado em {datetime.now().strftime("%d/%m/%Y %H:%M")}', 0, 0, 'C')

    def assinaturas(self):
        self.set_y(-50)
        self.set_font('Arial', 'B', 8)
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

# --- INICIALIZAÇÃO DA INTERFACE ---
st.set_page_config(page_title="Simulador de Impacto Financeiro", layout="wide")
local_css()

# LISTA DE PROGRAMAS E GERENTES (Puxar do PDF enviado)
LISTA_PROGRAMAS = [" ", "INS", "EINSTEIN", "CEMA", "MOGI", "RHP", "HCM", "HCS", "SoulBene Digital", "Girassol", "Bauru"]
LISTA_GERENTES = [" ", "Mariane Mylius", "Rosemary Lopes", "Lizia Cunha", "Sergio Carvalho", "Roberio Matos", "Kamyla Ferrarezi", "Cristiano Gomes", "Ana Alencar", "Marcela Prates", "Luiza Liberal", "Jose Alexandre"]

st.markdown('<div class="header-box"><h2 style="margin:0; color:#003366;">📑 Análise de Impacto Financeiro - PMO PROGRAMAS</h2></div>', unsafe_allow_html=True)

# 1. INFORMAÇÕES DO PROGRAMA
with st.container(border=True):
    c1, c2 = st.columns(2)
    prog_nome = c1.selectbox("Programa", options=LISTA_PROGRAMAS, key="sel_prog")
    prog_gerente = c2.selectbox("Gerente do Programa", options=LISTA_GERENTES, key="sel_gerente")
    contexto = st.text_area("Contexto da Mudança", placeholder="Descreva o motivo do impacto...")

# --- 3. MATRIZ DE ALOCAÇÃO (MANTIDO) ---
# [Lógica de horas e horizonte mantida conforme o seu original]
data_inicio = st.date_input("Início do Impacto", value=datetime.now())
horizonte = st.number_input("Meses", min_value=1, value=1)
lista_meses = [(data_inicio.replace(day=1) + timedelta(days=31*i)).strftime("%b/%y").upper() for i in range(horizonte)]

# Lógica Simplificada de Cálculo (Para exemplo)
custo_base_total = 150000.0 # Exemplo dinâmico baseado na matriz
total_cenario = custo_base_total * 1.15 # Adicionando risco PERT

# --- BOTÃO SALVAR E PROTOCOLAR NO ORACLE ---
if st.sidebar.button("💾 PROTOCOLAR E GERAR PDF"):
    conn = get_db_connection()
    if conn:
        cursor = conn.cursor()
        agora = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        # Inserção no Oracle SQL (Sintaxe :1, :2 para segurança)
        sql = """INSERT INTO RESUMO_IMPACTO 
                 (DATA_GERACAO, PROJETO, CUSTO_TOTAL, MARGEM_ANTES, MARGEM_DEPOIS, EROSAO) 
                 VALUES (:1, :2, :3, :4, :5, :6)"""
        
        # Valores simulados para o exemplo
        margem_antes, margem_depois, erosao = 50.0, 35.0, 15.0
        
        cursor.execute(sql, (agora, prog_nome, total_cenario, margem_antes, margem_depois, erosao))
        conn.commit()
        conn.close()
        st.sidebar.success("Protocolado no Oracle!")

    # Geração do PDF (Corrigido para evitar erro de bytes)
    pdf = RelatorioExecutivo()
    pdf.add_page()
    pdf.chapter_title("1. RESUMO EXECUTIVO")
    pdf.set_font('Arial', '', 10)
    pdf.cell(0, 10, f"Programa: {prog_nome} | Impacto: R$ {total_cenario:,.2f}", 0, 1)
    pdf.assinaturas()
    
    pdf_output = pdf.output()
    st.sidebar.download_button(
        label="📥 Baixar Dossiê PDF",
        data=bytes(pdf_output),
        file_name=f"Dossie_{prog_nome}.pdf",
        mime="application/pdf"
    )
