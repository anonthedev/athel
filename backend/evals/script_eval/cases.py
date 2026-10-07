from dataclasses import dataclass


@dataclass(frozen=True)
class Case:
    id: str
    question: str
    url: str
    note_groups: tuple[tuple[str, ...], ...]


CASES = (
    Case(
        id="marketplace",
        question="How does this store page describe the shelves, and what kind of storage does it call the bookcase?",
        url="https://www.ikea.com/us/en/cat/billy-bookcases-58288/",
        note_groups=(("adjustable shelves",), ("timeless storage",)),
    ),
    Case(
        id="blog",
        question="What date is printed at the top of the essay, and what does it say the reader is assumed to be?",
        url="https://paulgraham.com/greatwork.html",
        note_groups=(("July 2023",), ("very ambitious",)),
    ),
    Case(
        id="social",
        question="Which road does a comment ask about eating on, and what phrase does another comment use for the firm?",
        url="https://news.ycombinator.com/item?id=1",
        note_groups=(("Sandhill Road",), ("rising star",)),
    ),
    Case(
        id="recipe",
        question="What Celsius oven temperature does this cookie recipe give, and which sugar is beaten with the white sugar?",
        url="https://www.allrecipes.com/recipe/10813/best-chocolate-chip-cookies/",
        note_groups=(("175 degrees",), ("brown sugar",)),
    ),
    Case(
        id="reference",
        question="Who patented an early version of this brewer in France, and in what year?",
        url="https://en.wikipedia.org/wiki/French_press",
        note_groups=(("Delforge",), ("1852",)),
    ),
)
