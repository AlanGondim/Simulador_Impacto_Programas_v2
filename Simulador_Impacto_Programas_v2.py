import streamlit as st
import pandas as pd
import sqlite3
import numpy as np
import plotly.graph_objects as go
import plotly.express as px
from fpdf import FPDF
from datetime import datetime
import io
import os

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
    if o >= p: return np.full(n, m), float(m), float(m)
    sims = np.random.triangular(o, m, p, n)
    return sims, float(np.mean(sims)), float(np.percentile(sims, 95))

# Classe PDF Executiva Master
class ExecutivePDF(FPDF):
    def header(self):
        # Tenta incluir logo se existir
        if os.path.exists("Logomarca MV Atualizada.png"):
            self.image("Logomarca MV Atualizada.png", 10, 8, 33)
        self.set_font('Arial', 'B', 14)
        self.set_text_color(0, 51, 102)
        self.cell(0, 10, 'DOSSIE DE IMPACTO FINANCEIRO - GOVERNANCA MV', 0, 1, 'R')
        self.set_font('Arial', 'I', 8)
        self.cell(0, 5, f'Gerado em: {datetime.now().strftime("%d/%m/%Y %H:%M")}', 0, 1, 'R')
        self.ln(15)

    def chapter_title(self, label):
        self.set_font('Arial', 'B', 12)
        self.set_fill_color(230, 230, 230)
        self.cell(0, 8, label, 0, 1, 'L', fill=True)
        self.ln(4)

# --- INTERFACE ---
st.set_page_config(page_title="MV PMO Intelligence PRO", layout="wide")

with st.sidebar:
    st.header("⚙️ Parâmetros do Programa")
    proj = st.selectbox("Selecione o Projeto", [" ", "UNIMED SERRA GAUCHA", "INS", "CLINICA GIRASSOL", "EINSTEIN", "RHP"])
    receita_net = st.number_input("Receita Líquida (R$)", value=4719147.0, step=STEP_MACRO_MONEY)
    custo_eac_base = st.number_input("Custo Atual EAC (R$)", value=4963246.0, step=STEP_MACRO_MONEY)

tab1, tab2, tab3 = st.tabs(["🚀 Simulação Ativa", "📊 Sensibilidade & Erosão", "📚 Hub de Cenários"])

with tab1:
    st.subheader("1. Categorias de Impacto Técnico")
    cat_impacto = st.selectbox("Causa Raiz:", ["Replanejamento (Rollout)", "Retrabalho (Escopo)", "Instabilidade (Bugs)", "Infraestrutura (Ociosidade)"])
    
    impacto_calculado_cat = 0.0
    with st.container(border=True):
        col_c1, col_c2, col_c3 = st.columns(3)
        if cat_impacto == "Replanejamento (Rollout)":
            u = col_c1.number_input("Unidades Restantes", value=10, step=STEP_RESOURCE)
            b = col_c2.number_input("Burn Rate Mensal", value=150000.0, step=STEP_MACRO_MONEY)
            p_pace = col_c3.slider("Pace (Un/Mês)", 0.5, 5.0, 2.0)
            impacto_calculado_cat = (u / p_pace) * b
        elif cat_impacto == "Retrabalho (Escopo)":
            h = col_c1.number_input("H/H Estimada", value=200, step=STEP_RESOURCE)
            c = col_c2.number_input("Custo H/H", value=180.0, step=STEP_MONEY)
            impacto_calculado_cat = h * c
        elif cat_impacto == "Instabilidade (Bugs)":
            q = col_c1.number_input("Qtd de Chamados", value=50, step=STEP_RESOURCE)
            t = col_c2.number_input("Média Horas/Bug", value=8, step=STEP_RESOURCE)
            impacto_calculado_cat = q * t * 145.0
        elif cat_impacto == "Infraestrutura (Ociosidade)":
            d = col_c1.number_input("Dias de Bloqueio", value=5, step=STEP_RESOURCE)
            cd = col_c2.number_input("Custo Diário", value=12000.0, step=STEP_MACRO_MONEY)
            impacto_calculado_cat = d * cd

    st.subheader("2. Gestão de Recurso Adicional")
    with st.expander("➕ Vincular Novo Recurso"):
        with st.form("add_rec", clear_on_submit=True):
            f1, f2, f3 = st.columns([2,1,1])
            func = f1.selectbox("Função", ["Consultor Sr", "Analista Sr", "Gerente de Projeto Sr", "Desenvolvedor Sr", "Arquiteto de Soluções"])
            custo_h = f2.number_input("Custo/H", value=185.0, step=STEP_MONEY)
            horas_a = f3.number_input("Horas", value=160, step=STEP_RESOURCE)
            if st.form_submit_button("Confirmar Alocação"):
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
                c1.write(f"👤 **{row['funcao']}**")
                c2.write(f"{row['horas']}h x {format_currency(row['custo_h'])}")
                c3.write(f"**{format_currency(row['subtotal'])}**")
                if c4.button("🗑️", key=f"del_{row['id']}"):
                    db_conn.execute(f"DELETE FROM recursos WHERE id = {row['id']}")
                    db_conn.commit()
                    st.rerun()

    st.divider()
    m_nominal = impacto_calculado_cat + custo_staff
    sims_data, val_mean, val_p95 = run_monte_carlo(m_nominal * 0.9, m_nominal, m_nominal * 1.6)
    margem_original = (1 - (custo_eac_base / receita_net)) * 100 if receita_net > 0 else 0
    margem_f = (1 - ((custo_eac_base + val_p95) / receita_net)) * 100 if receita_net > 0 else 0

    res1, res2 = st.columns(2)
    with res1:
        st.metric("Impacto Financeiro P95 (Teto)", format_currency(val_p95), delta="Exposição Crítica")
        st.metric("Margem Projetada Pós-Impacto", f"{margem_f:.2f}%", delta=f"{margem_f - margem_original:.2f}%", delta_color="inverse")
        
        if st.button("📑 Gerar Dossiê de Aprovação (PDF)"):
            pdf = ExecutivePDF()
            pdf.add_page()
            
            # Seção 1: Dados do Projeto
            pdf.chapter_title("1. IDENTIFICACAO DO PROGRAMA")
            pdf.set_font("Arial", "", 10)
            data_info = [
                ["Projeto Selecionado:", proj],
                ["Receita Liquida (Net):", format_currency(receita_net)],
                ["Custo EAC Atual:", format_currency(custo_eac_base)],
                ["Margem Original:", f"{margem_original:.2f}%"]
            ]
            for row in data_info:
                pdf.cell(50, 7, row[0], 0)
                pdf.cell(0, 7, row[1], 0, 1)
            pdf.ln(5)

            # Seção 2: Análise de Impacto
            pdf.chapter_title("2. ANALISE TECNICA DE IMPACTO")
            pdf.set_font("Arial", "B", 10)
            pdf.cell(0, 7, f"Causa Raiz Identificada: {cat_impacto}", 0, 1)
            pdf.set_font("Arial", "", 10)
            pdf.multi_cell(0, 7, f"O impacto nominal calculado baseado nos parâmetros inseridos é de {format_currency(m_nominal)}. "
                                f"Considerando a volatilidade de mercado e riscos operacionais, o valor de exposição P95 (95% de confiança) é de {format_currency(val_p95)}.")
            pdf.ln(5)

            # Seção 3: Recursos Adicionais
            if not df_rec.empty:
                pdf.chapter_title("3. RECURSOS ADICIONAIS VINCULADOS")
                pdf.set_font("Arial", "B", 9)
                pdf.cell(80, 7, "Funcao", 1)
                pdf.cell(40, 7, "Horas", 1)
                pdf.cell(60, 7, "Subtotal", 1, 1)
                pdf.set_font("Arial", "", 9)
                for _, r in df_rec.iterrows():
                    pdf.cell(80, 7, r['funcao'], 1)
                    pdf.cell(40, 7, str(r['horas']), 1)
                    pdf.cell(60, 7, format_currency(r['subtotal']), 1, 1)
            
            pdf.ln(10)
            pdf.chapter_title("4. PARECER DE MARGEM E RISCO")
            pdf.set_font("Arial", "B", 12)
            pdf.set_text_color(200, 0, 0)
            pdf.cell(0, 10, f"MARGEM PROJETADA FINAL: {margem_f:.2f}%", 0, 1, 'C')
            
            # Exportando PDF
            pdf_bytes = pdf.output(dest='S')
            pdf_final = pdf_bytes.encode('latin-1') if isinstance(pdf_bytes, str) else bytes(pdf_bytes)
            st.download_button("📥 Baixar Dossiê Completo", data=pdf_final, file_name=f"Dossie_Impacto_{proj}.pdf", mime="application/pdf")

    with res2:
        # Radar Chart
        fig_radar = go.Figure()
        fig_radar.add_trace(go.Scatterpolar(r=[1,1,1,1], theta=['Custo','Prazo','Escopo','Custo'], fill='toself', name='Baseline'))
        cost_idx = val_p95/(m_nominal*1.2) if m_nominal>0 else 1.1
        fig_radar.add_trace(go.Scatterpolar(r=[cost_idx, 1.4, 1.3, cost_idx], theta=['Custo','Prazo','Escopo','Custo'], fill='toself', name='Impacto Real', line_color='red'))
        fig_radar.update_layout(polar=dict(radialaxis=dict(visible=True, range=[0, 2])), height=380, title="Triângulo de Ferro (Exposição)")
        st.plotly_chart(fig_radar, use_container_width=True)

with tab2:
    st.header("🔍 Histograma de Erosão e Sensibilidade")
    
    c1, c2 = st.columns(2)
    
    with c1:
        # Histograma de Monte Carlo (Erosão de Margem)
        margens_simuladas = (1 - ((custo_eac_base + sims_data) / receita_net)) * 100
        fig_hist = px.histogram(margens_simuladas, nbins=50, title="Histograma de Probabilidade: Margem Final",
                               labels={'value': 'Margem (%)'}, color_discrete_sequence=['#003366'])
        fig_hist.add_vline(x=margem_f, line_dash="dash", line_color="red", annotation_text="P95")
        st.plotly_chart(fig_hist, use_container_width=True)
        st.write(f"**Análise Visual:** A curva indica que há 95% de probabilidade da margem não cair abaixo de **{margem_f:.2f}%**.")

    with c2:
        # Gráfico de Composição
        data_s = [{'Origem': f"Causa: {cat_impacto}", 'Valor': impacto_calculado_cat}]
        if not df_rec.empty:
            for _, r in df_rec.iterrows(): data_s.append({'Origem': r['funcao'], 'Valor': r['subtotal']})
        
        df_plot = pd.DataFrame(data_s)
        fig_pie = px.sunburst(df_plot, path=['Origem'], values='Valor', title="Origem da Erosão Financeira", color='Valor', color_continuous_scale='Reds')
        st.plotly_chart(fig_pie, use_container_width=True)

with tab3:
    st.header("📚 Hub de Cenários de Governança")
    nome_s = st.text_input("Protocolo do Snapshot (Ex: Ajuste Crítico V1):")
    if st.button("💾 Protocolar Cenário"):
        db_conn.execute("INSERT INTO cenarios (projeto, nome_cenario, impacto_p95, margem, data) VALUES (?,?,?,?,?)",
                     (proj, nome_s, val_p95, margem_f, datetime.now().strftime("%d/%m %H:%M")))
        db_conn.commit()
        st.success("Snapshot salvo para auditoria.")
        
    st.subheader("Histórico de Simulações")
    df_h = pd.read_sql_query(f"SELECT * FROM cenarios WHERE projeto = '{proj}'", db_conn)
    st.dataframe(df_h[['nome_cenario', 'impacto_p95', 'margem', 'data']], use_container_width=True)
