from dataclasses import dataclass


@dataclass(frozen=True)
class Case:
    id: str
    url: str
    question: str
    # Marks the pages that carry the relevant passage. Other on-topic pages
    # may be included or dropped. `irrelevant` pages are the bibliography.
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
        relevant="800M",
        irrelevant=(10, 11, 12),
    ),
    Case(
        id="resnet",
        url="https://arxiv.org/pdf/1512.03385",
        question="What single-model top-5 validation error does the 152-layer ResNet report?",
        relevant="4.49%",
        irrelevant=(9,),
    ),
)
