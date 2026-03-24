import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from fpdf import FPDF
from datetime import datetime, timedelta
from PIL import Image
import io

# --- CONFIGURAÇÃO DA PÁGINA ---
st.set_page_config(page_title="PMO Impact Analyzer", layout="wide")

# --- ESTILIZAÇÃO CUSTOMIZADA ---
st.markdown("""
    <style>
    .main { background-color: #f8f9fa; }
    .stMetric { background-color: #ffffff; padding: 15px; border-radius: 10px; box-shadow: 0 2px 4px rgba(0,0,0,0.05); }
    </style>
    """, unsafe_allow_html=True)

# --- FUNÇÕES DE CÁLCULO (PERT) ---
def calc_pert(o, m, p):
    return (o + 4*m + p) / 6

def calc_std_dev(o, p):
    return (p - o) / 6

# --- SIDEBAR: CONFIGURAÇÕES E LOGO ---
try:
    logo = Image.open("Logomarca MV Atualizada.png")
    st.sidebar.image(logo, width=150)
except:
    st.sidebar.warning("Logo não encontrada. Verifique o arquivo.")

st.sidebar.title("Configurações do Programa")
proj_name = st.sidebar.text_input("Nome do Programa", "Migração ERP - MV")
manager = st.sidebar.text_input("Gerente Responsável", "Kamyla")
revenue = st.sidebar.number_input("Receita Líquida (R$)", value=4719147.0, step=1000.0)
current_cost = st.sidebar.number_input("Custo Atual EAC (R$)", value=4963246.0, step=1000.0)

# --- CORPO PRINCIPAL ---
st.title("📊 Painel de Gestão de Impacto & DRE")
st.info("Ferramenta de apoio à decisão para análise de mudanças e riscos financeiros.")

# 1. CATEGORIAS DE IMPACTO (HIDE AND SHOW)
st.subheader("1. Categorias de Impacto & Cenário")
categoria = st.selectbox("Selecione a Categoria de Mudança:", 
                        ["Replanejamento (Rollout)", "Retrabalho (Escopo)", "Instabilidade (Bugs)", "Infraestrutura (Ociosidade)"])

impacto_base = 0
impacto_risco = 0
meses_impacto = 1

with st.expander(f"Configurar Detalhes: {categoria}", expanded=True):
    col1, col2, col3 = st.columns(3)
    
    if categoria == "Replanejamento (Rollout)":
        escopo = col1.number_input("Qtd. Rollouts Restantes", value=11)
        pace_baseline = col2.number_input("Pace Original (Un/mês)", value=5.5)
        burn_rate = col3.number_input("Burn Rate Mensal Equipe (R$)", value=250000.0)
        
        o = st.slider("Pace Otimista", 1.0, 10.0, 6.0)
        m = st.slider("Pace Provável", 1.0, 10.0, 6.0)
        p = st.slider("Pace Pessimista", 1.0, 10.0, 4.0)
        
        dur_base = escopo / pace_baseline
        dur_pert = calc_pert(escopo/o, escopo/m, escopo/p)
        std_dev = calc_std_dev(escopo/o, escopo/p)
        dur_95 = dur_pert + (2 * std_dev)
        
        impacto_base = dur_base * burn_rate
        impacto_risco = (dur_95 - dur_base) * burn_rate
        meses_impacto = round(dur_95)

    elif categoria == "Retrabalho (Escopo)":
        itens = col1.number_input("Itens de Retrabalho", value=10)
        taxa_h = col2.number_input("Taxa Média Hora (R$)", value=120.0)
        
        o = col1.number_input("Horas/Item (Otimista)", value=4)
        m = col2.number_input("Horas/Item (Provável)", value=8)
        p = col3.number_input("Horas/Item (Pessimista)", value=16)
        
        total_h = itens * calc_pert(o, m, p)
        risco_h = itens * (2 * calc_std_dev(o, p))
        
        impacto_base = total_h * taxa_h
        impacto_risco = risco_h * taxa_h

    # Adicionar lógica similar para Bugs e Infra...
    else:
        st.write("Configurações simplificadas para este cenário...")
        impacto_base = st.number_input("Impacto Base Estimado (R$)", value=50000.0)
        impacto_risco = st.number_input("Reserva Delta PERT (R$)", value=15000.0)

orcamento_total = impacto_base + impacto_risco

# --- RESULTADOS FINANCEIROS ---
st.divider()
st.subheader("2. Análise de Custos e Margem")
c1, c2, c3 = st.columns(3)
c1.metric("Custo Estimado (Base)", f"R$ {impacto_base:,.2f}")
c2.metric("Reserva Delta PERT (Risco)", f"R$ {impacto_risco:,.2f}", delta="95% Confiança")
c3.metric("Orçamento Total Cenário", f"R$ {orcamento_total:,.2f}")

# --- DRE IMPACTO ---
st.subheader("3. Impacto na Margem Final (DRE)")
eac_novo = current_cost + orcamento_total
margem_atual = (1 - (current_cost / revenue)) * 100
margem_nova = (1 - (eac_novo / revenue)) * 100

col_dre1, col_dre2 = st.columns(2)
with col_dre1:
    st.write("**Resumo Financeiro**")
    df_dre = pd.DataFrame({
        "Indicador": ["Receita", "Custo Original", "Impacto Cenário", "Novo EAC"],
        "Valor (R$)": [revenue, current_cost, orcamento_total, eac_novo]
    })
    st.table(df_dre.style.format({"Valor (R$)": "R$ {:,.2f}"}))

with col_dre2:
    st.write("**Erosão de Margem**")
    st.metric("Margem Final Projetada", f"{margem_nova:.2f}%", 
              delta=f"{margem_nova - margem_atual:.2f} p.p.", delta_color="inverse")

# --- TRIÂNGULO DE FERRO ---
st.subheader("4. Análise Integrada: Triângulo de Ferro")
# Simulação de eixos (1.0 é a base estável)
cost_idx = orcamento_total / (current_cost * 0.1) if current_cost > 0 else 1.0 # Sensibilidade
time_idx = 1.2 if impacto_risco > 0 else 1.0
scope_idx = 1.3 if categoria == "Retrabalho (Escopo)" else 1.1

fig = go.Figure()
fig.add_trace(go.Scatterpolar(
      r=[1, 1, 1, 1], theta=['Custo', 'Prazo', 'Escopo', 'Custo'],
      fill='toself', name='Baseline', line_color='blue'
))
fig.add_trace(go.Scatterpolar(
      r=[cost_idx, time_idx, scope_idx, cost_idx],
      theta=['Custo', 'Prazo', 'Escopo', 'Custo'],
      fill='toself', name='Projetado', line_color='red'
))
fig.update_layout(polar=dict(radialaxis=dict(visible=True, range=[0, 2])), showlegend=True)
st.plotly_chart(fig)

# --- GERADOR DE RELATÓRIO PDF ---
class PDF(FPDF):
    def header(self):
        if 'logo' in globals() or 'logo' in locals():
            with io.BytesIO() as output:
                logo.save(output, format="PNG")
                self.image(io.BytesIO(output.getvalue()), 10, 8, 20)
        self.set_font('Arial', 'B', 12)
        self.cell(80)
        self.cell(30, 10, f'Relatorio Executivo - {proj_name}', 0, 0, 'C')
        self.ln(20)
        
    def footer(self):
        self.set_y(-15)
        self.set_font('Arial', 'I', 8)
        self.cell(0, 10, 'Desenvolvido por PMO Corporativo de Programas', 0, 0, 'C')
        self.set_text_color(200, 200, 200)
        self.text(50, 150, "CONFIDENTIAL")

def generate_pdf():
    pdf = PDF()
    pdf.add_page()
    pdf.set_font("Arial", size=10)
    pdf.cell(200, 10, txt=f"Data do Relatório: {datetime.now().strftime('%d/%m/%Y')}", ln=True)
    pdf.cell(200, 10, txt=f"Gerente: {manager}", ln=True)
    pdf.ln(10)
    pdf.set_font("Arial", 'B', 14)
    pdf.cell(200, 10, txt="Resumo do Impacto", ln=True)
    pdf.set_font("Arial", size=11)
    pdf.cell(200, 10, txt=f"Categoria: {categoria}", ln=True)
    pdf.cell(200, 10, txt=f"Orcamento Adicional (Base + Risco): R$ {orcamento_total:,.2f}", ln=True)
    pdf.cell(200, 10, txt=f"Margem Final Projetada: {margem_nova:.2f}%", ln=True)
    pdf.ln(10)
    pdf.multi_cell(0, 10, txt="Analise Executiva: O impacto apresentado considera a metodologia PERT para calculo de incertezas. Recomenda-se a aprovacao da reserva de contingencia para evitar paralisacao das frentes de trabalho.")
    return pdf.output(dest='S')

if st.button("Gerar Relatório Executivo (PDF)"):
    pdf_bytes = generate_pdf()
    
    # Adicionamos uma verificação simples e passamos os bytes diretamente
    st.download_button(
        label="Clique aqui para Baixar Relatório A4",
        data=pdf_bytes,
        file_name=f"Relatorio_Impacto_{datetime.now().strftime('%Y%m%d')}.pdf",
        mime="application/pdf"
    )
