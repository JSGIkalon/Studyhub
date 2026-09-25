# Varios nombres llevan guion largo porque asi vienen del curriculo. Cambiarlos
# por un guion normal los desalinearia de la base de datos y del Excel, y el
# sincronizador los veria como modulos distintos.
# ruff: noqa: RUF001
"""Temario oficial del CFA Level I, tal como debe quedar en la aplicacion.

Esto es **datos, no codigo**: la lista de Learning Modules por tema, en su orden.
Vive en `herramientas/` y no dentro de `mukuwareru/` a proposito — la aplicacion
no trae ningun temario cableado, se lo da el usuario. Esto solo alimenta a
`sincronizar_temario.py`.

El curriculo se renumera cada ano. Cuando cambie, se edita esta lista y se vuelve
a pasar el sincronizador; el estado «completado» se conserva por nombre.
"""

from __future__ import annotations

# Nombre de la materia **tal como esta en la base de datos** -> sus modulos.
# Las claves no son los nombres oficiales largos («Ethical and Professional
# Standards», «Financial Statement Analysis») porque son las etiquetas que el
# usuario ve en la barra del Pomodoro y en Progreso, y ahi lo corto gana.
TEMARIO: dict[str, tuple[str, ...]] = {
    "Ethics": (
        "Ethics and Trust in the Investment Profession",
        "Code of Ethics and Standards of Professional Conduct",
        "Guidance for Standards I–VII",
        "Introduction to the Global Investment Performance Standards (GIPS)",
        "Ethics Application",
    ),
    "Quantitative Methods": (
        "Rates and Returns",
        "Time Value of Money in Finance",
        "Statistical Measures of Asset Returns",
        "Probability Trees and Conditional Expectations",
        "Portfolio Mathematics",
        "Simulation Methods",
        "Estimation and Inference",
        "Hypothesis Testing",
        "Parametric and Non-Parametric Tests of Independence",
        "Simple Linear Regression",
        "Introduction to Big Data Techniques",
    ),
    "Economics": (
        "The Firm and Market Structures",
        "Understanding Business Cycles",
        "Fiscal Policy",
        "Monetary Policy",
        "Introduction to Geopolitics",
        "International Trade",
        "Capital Flows and the FX Market",
        "Exchange Rate Calculations",
    ),
    "Corporate Issuers": (
        "Organizational Forms, Corporate Issuer Features, and Ownership",
        "Investors and Other Stakeholders",
        "Corporate Governance: Conflicts, Mechanisms, Risks, and Benefits",
        "Working Capital and Liquidity",
        "Capital Investments and Capital Allocation",
        "Capital Structure",
        "Business Models",
    ),
    "FSA": (
        "Introduction to Financial Statement Analysis",
        "Analyzing Income Statements",
        "Analyzing Balance Sheets",
        "Analyzing Statements of Cash Flows I",
        "Analyzing Statements of Cash Flows II",
        "Analysis of Inventories",
        "Analysis of Long-Term Assets",
        "Topics in Long-Term Liabilities and Equity",
        "Analysis of Income Taxes",
        "Financial Reporting Quality",
        "Financial Analysis Techniques",
        "Introduction to Financial Statement Modeling",
    ),
    "Equity Investments": (
        "Market Organization and Structure",
        "Security Market Indexes",
        "Market Efficiency",
        "Overview of Equity Securities",
        "Company Analysis: Past and Present",
        "Industry and Competitive Analysis",
        "Company Analysis: Forecasting",
        "Equity Valuation: Concepts and Basic Tools",
    ),
    "Fixed Income": (
        "Fixed-Income Instrument Features",
        "Fixed-Income Cash Flows and Types",
        "Fixed-Income Issuance and Trading",
        "Fixed-Income Markets for Corporate Issuers",
        "Fixed-Income Markets for Government Issuers",
        "Fixed-Income Bond Valuation: Prices and Yields",
        "Yield and Yield Spread Measures for Fixed-Rate Bonds",
        "Yield and Yield Spread Measures for Floating-Rate Instruments",
        "The Term Structure of Interest Rates: Spot, Par, and Forward Curves",
        "Interest Rate Risk and Return",
        "Yield-Based Bond Duration Measures and Properties",
        "Yield-Based Bond Convexity and Portfolio Properties",
        "Curve-Based and Empirical Fixed-Income Risk Measures",
        "Credit Risk",
        "Credit Analysis for Government Issuers",
        "Credit Analysis for Corporate Issuers",
        "Fixed-Income Securitization",
        "Asset-Backed Security (ABS) Instrument and Market Features",
        "Mortgage-Backed Security (MBS) Instrument and Market Features",
    ),
    "Derivatives": (
        "Derivative Instrument and Derivative Market Features",
        "Forward Commitment and Contingent Claim Features and Instruments",
        "Derivative Benefits, Risks, and Issuer and Investor Uses",
        "Arbitrage, Replication, and the Cost of Carry in Pricing Derivatives",
        "Pricing and Valuation of Forward Contracts and for an Underlying with "
        "Varying Maturities",
        "Pricing and Valuation of Futures Contracts",
        "Pricing and Valuation of Interest Rates and Other Swaps",
        "Pricing and Valuation of Options",
        "Option Replication Using Put–Call Parity",
        "Valuing a Derivative Using a One-Period Binomial Model",
    ),
    "Alternative Investments": (
        "Alternative Investment Features, Methods, and Structures",
        "Alternative Investment Performance and Returns",
        "Investments in Private Capital: Equity and Debt",
        "Real Estate and Infrastructure",
        "Natural Resources",
        "Hedge Funds",
        "Introduction to Digital Assets",
    ),
    "Portfolio Management": (
        "Portfolio Risk and Return: Part I",
        "Portfolio Risk and Return: Part II",
        "Portfolio Management: An Overview",
        "Basics of Portfolio Planning and Construction",
        "The Behavioral Biases of Individuals",
        "Introduction to Risk Management",
    ),
}

# Modulos que **son el mismo** con otro nombre. Se renombran antes de reconciliar
# para no perder su «completado»: borrarlos y crearlos de nuevo reiniciaria el
# progreso y la fecha en que se lograron.
#
# Solo hace falta una entrada cuando el nombre viejo no esta en TEMARIO y el
# modulo importa; si nadie lo completo, da igual renombrarlo o recrearlo.
RENOMBRADOS: dict[tuple[str, str], str] = {
    # El curriculo nuevo sustituye este LM por «Financial Analysis Techniques» e
    # «Introduction to Financial Statement Modeling». Se renombra al primero para
    # no perder que estaba completado; el segundo nace completado por estar FSA
    # en TEMAS_COMPLETOS.
    ("FSA", "Applications of Financial Statement Analysis"):
        "Financial Analysis Techniques",
    # La «y» espanola se colo en un nombre en ingles. Esta completado.
    ("Corporate Issuers", "Corporate Governance: Conflicts, Mechanisms, Risks y Benefits"):
        "Corporate Governance: Conflicts, Mechanisms, Risks, and Benefits",
    # El curriculo 2024 partio este LM en tres; el original pasa a ser el primero
    # y los otros dos se crean detras.
    ("Equity Investments", "Introduction to Industry and Company Analysis"):
        "Company Analysis: Past and Present",
    # Anotaciones propias que no forman parte del nombre oficial.
    ("Ethics", "Guidance for Standards I–VII (aplicación de casos)"):
        "Guidance for Standards I–VII",
    ("Ethics", "Ethics Application — casos y Qbank dirigido"):
        "Ethics Application",
}


# Temas que el usuario ya termino. Un modulo **nuevo** de uno de estos temas nace
# marcado como completado: si el curriculo parte en dos un LM que ya se estudio,
# dejar el nuevo pendiente diria que falta algo que en realidad esta hecho.
#
# Solo afecta a los modulos que el sincronizador crea. No toca los que ya estan,
# asi que desmarcar algo a mano en la aplicacion no se deshace al volver a pasar
# la herramienta.
TEMAS_COMPLETOS: frozenset[str] = frozenset(
    {
        "Quantitative Methods",
        "Economics",
        "Corporate Issuers",
        "FSA",
    }
)


def total() -> int:
    """Cuantos modulos tiene el temario completo."""
    return sum(len(modulos) for modulos in TEMARIO.values())
