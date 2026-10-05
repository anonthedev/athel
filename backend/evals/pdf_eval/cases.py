from dataclasses import dataclass


@dataclass(frozen=True)
class Case:
    id: str
    url: str
    question: str
    # Marks the pages that carry the relevant passage. Other on-topic pages
    # may be included or dropped. `irrelevant` pages are a bibliography, or
    # other back matter that does not answer the question. An empty tuple
    # means this PDF has no such pages.
    relevant: str
    irrelevant: tuple[int, ...]


CASES = (
    Case(
        id="attention",
        url="https://arxiv.org/pdf/1706.03762",
        question="How many parallel attention heads does the Transformer use in this work?",
        relevant="h = 8",
        irrelevant=(11, 12),
    ),
    Case(
        id="bert",
        url="https://arxiv.org/pdf/1810.04805",
        question="How many words are in the BooksCorpus used to pre-train BERT?",
        relevant="BooksCorpus (800M words)",
        irrelevant=(10, 11),
    ),
    Case(
        id="resnet",
        url="https://arxiv.org/pdf/1512.03385",
        question="What single-model top-5 validation error does the 152-layer ResNet report?",
        relevant="4.49%",
        irrelevant=(9,),
    ),
    Case(
        id="adam",
        url="https://arxiv.org/pdf/1412.6980",
        question="What default value of beta2 does Adam use?",
        relevant="0.999",
        irrelevant=(11,),
    ),
    Case(
        id="batchnorm",
        url="https://arxiv.org/pdf/1502.03167",
        question="What training problem does batch normalization aim to reduce?",
        relevant="internal covariate shift",
        irrelevant=(9,),
    ),
    Case(
        id="yolo",
        url="https://arxiv.org/pdf/1506.02640",
        question="How many frames per second does the base YOLO model process?",
        relevant="45 frames",
        irrelevant=(9, 10),
    ),
    Case(
        id="gan",
        url="https://arxiv.org/pdf/1406.2661",
        question="What does this paper call the pair of networks trained against each other?",
        relevant="generative adversarial",
        irrelevant=(9,),
    ),
    Case(
        id="gnn",
        url="https://arxiv.org/pdf/1810.00826",
        question="Which classical graph test is this paper's analysis of graph neural networks built on?",
        relevant="Weisfeiler-Lehman",
        irrelevant=(12, 13),
    ),
    Case(
        id="dropout",
        url="https://arxiv.org/pdf/1207.0580",
        question="What regularization method does this paper introduce?",
        relevant="Dropout",
        irrelevant=(7,),
    ),
    Case(
        id="ligo",
        url="https://arxiv.org/pdf/1602.03837",
        question="What name is given to the gravitational-wave signal reported here?",
        relevant="GW150914",
        irrelevant=(10,),
    ),
    Case(
        id="higgs",
        url="https://arxiv.org/pdf/1207.7214",
        question="At what mass does ATLAS report the observed Higgs-like signal?",
        relevant="126 GeV",
        irrelevant=(23, 24, 25),
    ),
    Case(
        id="planck",
        url="https://arxiv.org/pdf/1807.06209",
        question="What Hubble constant does Planck infer, in km/s/Mpc?",
        relevant="67.4",
        irrelevant=(63, 64, 65, 66, 67, 68, 69),
    ),
    Case(
        id="alphafold",
        url="https://rcastoragev2.blob.core.windows.net/79deebd6096b05aec00813b7000c010a/PMC8371605.pdf",
        question="What median backbone accuracy, in angstroms, did AlphaFold report on CASP14?",
        relevant="0.96",
        irrelevant=(11, 12),
    ),
    Case(
        id="crispr",
        url="https://computingbiology.github.io/docs/jinek2012.pdf",
        question="Which Cas9 domain cleaves the noncomplementary DNA strand?",
        relevant="RuvC",
        irrelevant=(6,),
    ),
    Case(
        id="pubchem",
        url="https://rcastoragev2.blob.core.windows.net/39e8a93539008711575ecbefc5299a7e/PMC4702940.pdf",
        question="How many unique chemical structures did PubChem report in this paper?",
        relevant="60 million",
        irrelevant=(12,),
    ),
    Case(
        id="mpnn",
        url="https://arxiv.org/pdf/1704.01212",
        question="How many molecules are in the QM9 benchmark used here?",
        relevant="130k",
        irrelevant=(9,),
    ),
    Case(
        id="zhang",
        url="https://annals.math.princeton.edu/wp-content/uploads/annals-v179-n3-p07-p.pdf",
        question="What upper bound does Zhang prove on the liminf gap between consecutive primes?",
        relevant="7 × 10",
        irrelevant=(54,),
    ),
    Case(
        id="greentao",
        url="https://arxiv.org/pdf/math/0404188",
        question="What does Green and Tao prove about arithmetic progressions of primes?",
        relevant="arbitrarily long",
        irrelevant=(56,),
    ),
    Case(
        id="perelman",
        url="https://arxiv.org/pdf/math/0211159",
        question="What kind of formula does Perelman introduce for Ricci flow?",
        relevant="entropy",
        irrelevant=(39,),
    ),
    Case(
        id="kepler",
        url="https://arxiv.org/pdf/1501.02155",
        question="How many CPU hours does the hardest Kepler subclaim take to verify?",
        relevant="5000 CPU",
        irrelevant=(19, 20, 21),
    ),
    Case(
        id="reproducibility",
        url="https://discovery.dundee.ac.uk/ws/files/7385883/RPP_SCIENCE_2015.pdf",
        question="What percentage of replications were significant in the original direction?",
        relevant="36%",
        irrelevant=(29, 30),
    ),
    Case(
        id="henrich",
        url="https://www2.psych.ubc.ca/~henrich/pdfs/WeirdPeople.pdf",
        question="What does the acronym WEIRD stand for in this paper?",
        relevant="Western, Educated",
        irrelevant=(73, 74, 75),
    ),
    Case(
        id="chexnet",
        url="https://arxiv.org/pdf/1711.05225",
        question="Which chest X-ray dataset was CheXNet trained on?",
        relevant="ChestX-ray14",
        irrelevant=(6, 7),
    ),
    Case(
        id="economist",
        url="https://arxiv.org/pdf/2108.02755",
        question="What labor-supply elasticity does the Saez-tax regression estimate?",
        relevant="0.87",
        irrelevant=(32, 33),
    ),
    Case(
        id="ipcc",
        url="https://www.ipcc.ch/report/ar6/wg1/downloads/report/IPCC_AR6_WGI_SPM.pdf",
        question="How much higher, in degrees Celsius, was global surface temperature in 2011-2020 than in 1850-1900?",
        relevant="1.09",
        irrelevant=(),
    ),
)
