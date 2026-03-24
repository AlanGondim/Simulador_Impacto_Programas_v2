import streamlit as st
import pandas as pd
import sqlite3
import matplotlib.pyplot as plt
import seaborn as sns
import numpy as np
from fpdf import FPDF
from datetime import datetime
import tempfile
import os
from PIL import Image
import io

# --- CONFIGURAÇÕES INICIAIS ---
st.set_page_config(page_title="🛡️ MV PMO Impact Simulator", layout="wide")

# --- FUNÇÕES DE APOIO ---
def format_moeda(valor):
    return f"R$ {valor:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")

def calcular_pert(o, m, p):
    return (o + 4 * m + p) / 6

def simular_monte_carlo(o, m, p, n=2000):
    if o >= p: return m, m
    simulacoes = np.random.triangular(o, m, p, n)
    return np.mean(simulacoes), np.percentile(simulacoes, 95)

# --- BANCO DE DADOS (PERSISTÊNCIA DE RECURSOS E HISTÓRICO) ---
def init_db():
    conn = sqlite3.connect('mv_pmo_simulator.db', check_same_thread=False)
    cursor = conn.cursor()
    # Tabela de Recursos (Alocação)
    cursor.execute('''CREATE TABLE IF NOT EXISTS recursos_projeto 
        (id INTEGER PRIMARY KEY AUTOINCREMENT, projeto TEXT, funcao TEXT, 
        senioridade TEXT, custo_hora REAL, horas INTEGER, subtotal REAL, data_registro TEXT)''')
    # Tabela de Histórico (Pareceres)
    cursor.execute('''CREATE TABLE IF NOT EXISTS historico_pareceres 
        (id INTEGER PRIMARY KEY AUTOINCREMENT, projeto TEXT, gerente TEXT, categoria TEXT, justificativa TEXT, 
        receita REAL, custos_atuais REAL, margem_anterior REAL, impacto_financeiro REAL, 
        p_otimista REAL, p_pessimista REAL, p_pert_resultado REAL, 
        d_otimista REAL, d_provavel REAL, d_pessimista REAL, d_pert_resultado REAL,
        p_mc_resultado REAL, total_horas INTEGER, data_emissao TEXT)''')
    conn.commit()
    return conn

conn = init_db()

# --- CLASSE PDF EXECUTIVA COM LOGO E WATERMARK ---
class ExecutiveReport(FPDF):
    def __init__(self, dados, df_recursos=None, logo_path=None):
        super().__init__()
        self.d = dados
        self.df_recursos = df_recursos
        self.logo_path = logo_path

    def header(self):
        # Cabeçalho Azul Escuro
        self.set_fill_color(0, 51, 102); self.rect(0, 0, 210, 40, 'F')
        
        # Logo Discreta à Esquerda
        if self.logo_path and os.path.exists(self.logo_path):
            self.image(self.logo_path, 10, 8, 25)
        
        # Marca d'água Confidential
        self.set_font('Arial', 'B', 50); self.set_text_color(240, 240, 240)
        with self.rotation(45, 100, 150):
            self.text(40, 190, "CONFIDENTIAL")
        
        self.set_font("Arial", 'B', 14); self.set_text_color(255)
        self.set_y(12); self.cell(0, 10, "DOSSIÊ DE IMPACTO E GOVERNANÇA ECONÔMICA", ln=True, align='R')
        self.set_font("Arial", '', 9)
        self.cell(0, 5, f"PROGRAMA: {self.d['projeto']} | EMISSÃO: {datetime.now().strftime('%d/%m/%Y %H:%M')}", ln=True, align='R')
        self.ln(20)

    def footer(self):
        self.set_y(-25)
        self.set_font("Arial", 'I', 8); self.set_text_color(100)
        self.cell(0, 10, "Desenvolvido por PMO Corporativo de Programas", 0, 0, 'C')
        self.set_y(-15)
        # Assinaturas
        self.set_font("Arial", 'B', 8); self.set_text_color(0)
        self.line(30, self.get_y(), 90, self.get_y())
        self.line(120, self.get_y(), 180, self.get_y())
        self.text(45, self.get_y()+4, "GERENTE DO PROGRAMA")
        self.text(135, self.get_y()+4, "DIRETOR DE OPERAÇÕES")

    def section_title(self, title):
        self.set_font("Arial", 'B', 11); self.set_fill_color(240, 240, 240); self.set_text_color(0, 51, 102)
        self.cell(0, 8, f" {title}", ln=True, fill=True); self.ln(3)

# --- INTERFACE STREAMLIT ---
st.sidebar.markdown("### 🛡️ MV PMO Master")
menu = st.sidebar.radio("Navegação", ["Nova Análise de Impacto", "Hub de Dossiês"])

# Carregar Logo para uso no PDF
LOGO_FILE = "Logomarca MV Atualizada.png"

if menu == "Nova Análise de Impacto":
    st.title("📊 Simulador de Impacto e Alocação")
    
    # 1. CABEÇALHO DO PROGRAMA
    with st.container():
        c1, c2, c3 = st.columns([2, 1, 1])
        nome_projeto = c1.selectbox("Programa / Cliente", [" ", "UNIMED SERRA GAÚCHA", "UNIMED NORTE FLUMINENSE", "CLÍNICA GIRASSOL", "EINSTEIN", "SESA/ES", "RHP"])
        receita = c2.number_input("Receita Líquida (R$)", min_value=0.0, step=1000.0)
        custos_atuais = c3.number_input("Custos Atuais EAC (R$)", min_value=0.0, step=1000.0)
        
        gerente = st.text_input("Gerente Responsável")
        cat_impacto = st.multiselect("Categoria do Impacto", ["Replanejamento", "Retrabalho", "Bugs/Instabilidade", "Ociosidade Infra", "Escopo Adicional"])
        justificativa = st.text_area("Justificativa Técnica")

    st.divider()

    # 2. ALOCAÇÃO DE RECURSOS (HIDE/SHOW VIA EXPANDER)
    st.subheader("👥 Alocação de Recursos e Esforço")
    with st.expander("➕ Adicionar Recurso ao Cenário", expanded=True):
        with st.form("form_recurso"):
            f1, f2, f3, f4 = st.columns([2, 1, 1, 1])
            func = f1.selectbox("Função", ["Consultor", "Analista", "Desenvolvedor", "Gerente de Projetos"])
            seni = f2.selectbox("Sênioridade", ["Jr", "Pl", "Sr", "Esp"])
            vh = f3.number_input("Custo/Hora (R$)", value=120.0)
            hrs = f4.number_input("Horas Estimadas", min_value=1)
            if st.form_submit_button("Alocar Recurso"):
                conn.execute("INSERT INTO recursos_projeto (projeto, funcao, senioridade, custo_hora, horas, subtotal, data_registro) VALUES (?,?,?,?,?,?,?)",
                             (nome_projeto, func, seni, vh, hrs, vh*hrs, datetime.now().isoformat()))
                conn.commit()
                st.rerun()

    # Visualização e Edição
    df_rec = pd.read_sql_query(f"SELECT * FROM recursos_projeto WHERE projeto = '{nome_projeto}'", conn)
    if not df_rec.empty:
        st.dataframe(df_rec[['funcao', 'senioridade', 'custo_hora', 'horas', 'subtotal']], use_container_width=True)
        if st.button("🗑️ Limpar Alocação Atual"):
            conn.execute(f"DELETE FROM recursos_projeto WHERE projeto = '{nome_projeto}'")
            conn.commit()
            st.rerun()

        total_nominal = df_rec['subtotal'].sum()
        total_horas = df_rec['horas'].sum()

        # 3. ANÁLISE DE EROSÃO E RISCO
        st.divider()
        col_res1, col_res2 = st.columns(2)
        
        with col_res1:
            st.subheader("📉 Impacto na Margem")
            m_ant = ((receita - custos_atuais) / receita * 100) if receita > 0 else 0
            m_pos = (((receita - custos_atuais) - total_nominal) / receita * 100) if receita > 0 else 0
            
            fig, ax = plt.subplots(figsize=(6, 3))
            sns.barplot(x=['Atual', 'Pós-Impacto'], y=[m_ant, m_pos], palette=['#003366', '#C0392B'], ax=ax)
            ax.set_ylabel("Margem (%)")
            st.pyplot(fig)
            st.metric("Erosão de Margem", f"{m_pos:.2f}%", f"{m_pos - m_ant:.2f}%", delta_color="inverse")

        with col_res2:
            st.subheader("🎲 Modelagem de Risco (PERT)")
            c_ot = st.number_input("Custo Otimista (R$)", value=total_nominal * 0.8)
            c_pe = st.number_input("Custo Pessimista (R$)", value=total_nominal * 1.5)
            res_pert = calcular_pert(c_ot, total_nominal, c_pe)
            _, p95_mc = simular_monte_carlo(c_ot, total_nominal, c_pe)
            
            st.info(f"**Custo Médio PERT:** {format_moeda(res_pert)}")
            st.warning(f"**Teto de Risco (P95):** {format_moeda(p95_mc)}")

        if st.button("🚀 FINALIZAR E PROTOCOLAR DOSSIÊ"):
            sql = '''INSERT INTO historico_pareceres (projeto, gerente, categoria, justificativa, receita, custos_atuais, margem_anterior, impacto_financeiro, p_otimista, p_pessimista, p_pert_resultado, p_mc_resultado, total_horas, data_emissao) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)'''
            conn.execute(sql, (nome_projeto, gerente, ", ".join(cat_impacto), justificativa, receita, custos_atuais, m_ant, total_nominal, c_ot, c_pe, res_pert, p95_mc, int(total_horas), datetime.now().isoformat()))
            conn.commit()
            st.success("Dossiê protocolado com sucesso no Hub!")

else:
    st.title("📚 Hub de Inteligência Corporativa")
    df_h = pd.read_sql_query("SELECT * FROM historico_pareceres ORDER BY data_emissao DESC", conn)
    
    for i, row in df_h.iterrows():
        with st.expander(f"📋 {row['projeto']} - {row['data_emissao'][:10]} | PERT: {format_moeda(row['p_pert_resultado'])}"):
            st.write(f"**Gerente:** {row['gerente']}")
            st.write(f"**Justificativa:** {row['justificativa']}")
            
            if st.button(f"📥 Baixar Dossiê PDF", key=f"pdf_{row['id']}"):
                pdf = ExecutiveReport(row.to_dict(), logo_path=LOGO_FILE)
                pdf.add_page()
                
                # Seção 1: Resumo
                pdf.section_title("1. RESUMO DO IMPACTO")
                pdf.set_font("Arial", '', 10)
                pdf.multi_cell(0, 6, f"Categoria: {row['categoria']}\nJustificativa: {row['justificativa']}")
                
                # Seção 2: Financeiro
                pdf.ln(5)
                pdf.section_title("2. PERFORMANCE FINANCEIRA (DRE)")
                pdf.cell(95, 8, f"Receita Base: {format_moeda(row['receita'])}")
                pdf.cell(95, 8, f"Margem Original: {row['margem_anterior']:.2f}%", ln=True)
                pdf.cell(95, 8, f"Impacto Nominal: {format_moeda(row['impacto_financeiro'])}")
                pdf.cell(95, 8, f"Custo PERT (Projetado): {format_moeda(row['p_pert_resultado'])}", ln=True)
                
                # Seção 3: Recursos
                pdf.ln(5)
                pdf.section_title("3. ANALÍTICO DE ALOCAÇÃO")
                df_rec_h = pd.read_sql_query(f"SELECT funcao, senioridade, horas, subtotal FROM recursos_projeto WHERE projeto = '{row['projeto']}'", conn)
                pdf.set_font("Arial", 'B', 9)
                pdf.cell(60, 7, "Função", 1); pdf.cell(40, 7, "Sênior.", 1); pdf.cell(30, 7, "Horas", 1); pdf.cell(60, 7, "Subtotal", 1); pdf.ln()
                pdf.set_font("Arial", '', 9)
                for _, r in df_rec_h.iterrows():
                    pdf.cell(60, 7, r['funcao'], 1); pdf.cell(40, 7, r['senioridade'], 1); pdf.cell(30, 7, str(r['horas']), 1); pdf.cell(60, 7, format_moeda(r['subtotal']), 1); pdf.ln()
                
                # Rodapé do PDF
                pdf_output = pdf.output(dest='S')
                st.download_button("Clique aqui para salvar o PDF", pdf_output, f"Dossie_{row['projeto']}.pdf", "application/pdf")
