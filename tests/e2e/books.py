# Copyright (C) 2026 Theo van Oostrum
"""The fixture books of the e2e suite, and the cross-book question for each set.

The tiny books are for the required run with the fakes. The live books are
larger, for the live run against the real providers: three books with a few
chapters each, and distractor passages that share words with the question
but do not answer it. Both sets are generated from this file, so every run
uses the same books and the repo holds no binary EPUBs.
"""

import dataclasses
import uuid
from dataclasses import dataclass

from tests.epubs import FixtureBook, FixtureChapter, paragraphs


@dataclass(frozen=True)
class Library:
    """A set of books, and a question that needs the first two of them.

    The third book is never selected, so a test can check that search keeps
    to the selected books.
    """

    books: tuple[FixtureBook, FixtureBook, FixtureBook]
    question: str


def fresh(book: FixtureBook) -> FixtureBook:
    """Return `book` with a new identifier.

    A new identifier gives a new file, so the books can be uploaded again to
    a stack that already holds them.
    """
    return dataclasses.replace(book, identifier=f"urn:uuid:{uuid.uuid4()}")


def _chapter(title: str, *texts: str) -> FixtureChapter:
    return FixtureChapter(f"<h1>{title}</h1>{paragraphs(*texts)}", nav_title=title)


TINY = Library(
    books=(
        FixtureBook(
            title="The Quiet Hive",
            author="Mira Comb",
            chapters=(
                _chapter(
                    "Autumn",
                    "Before winter the beekeeper narrows the hive entrance "
                    "with a wooden reducer, so mice stay out.",
                ),
                _chapter(
                    "Winter",
                    "In winter the bees cluster around the queen and eat "
                    "the honey they stored in summer.",
                ),
            ),
        ),
        FixtureBook(
            title="The Gannet Rock Light",
            author="Tom Wick",
            chapters=(
                _chapter(
                    "Stores",
                    "Before winter the lighthouse keeper fills the oil store "
                    "and stacks dry wood for the stove.",
                ),
                _chapter(
                    "Storms",
                    "In winter storms the keeper winds the lamp's clockwork "
                    "every two hours through the night.",
                ),
            ),
        ),
        FixtureBook(
            title="Fire Under the Mountain",
            author="Ana Basalt",
            chapters=(
                _chapter(
                    "Ash",
                    "Before winter the volcano wardens clear ash from the "
                    "roads below the crater.",
                ),
            ),
        ),
    ),
    question="How do beekeepers and lighthouse keepers get ready for winter?",
)

LIVE = Library(
    books=(
        FixtureBook(
            title="The Lamp at Gannet Rock",
            author="Elsie Harrow",
            chapters=(
                _chapter(
                    "The Rock",
                    "Gannet Rock stands four miles off the headland, a black "
                    "spine of stone that the sea covers at every spring tide. "
                    "The tower was finished in 1871, and for ninety years three "
                    "keepers lived on it at a time, two on watch and one ashore "
                    "on leave. The relief boat came every fortnight when the "
                    "weather allowed, and in a bad winter it did not come for "
                    "six weeks.",
                    "The keepers' quarters were three round rooms stacked one "
                    "above the other: the kitchen with its iron stove, the "
                    "bedroom with curved bunks built against the wall, and the "
                    "store room where the oil, the wicks and the spare glass "
                    "were kept. Above them all was the lantern room, where the "
                    "great lens turned.",
                    "Nobody chose Gannet Rock for the view. Most keepers asked "
                    "for it because the pay was a little better than on a shore "
                    "station, and because a man on a rock, it was said, had no "
                    "one to answer to but the weather.",
                ),
                _chapter(
                    "Keeping the Light",
                    "The lamp burned paraffin, and the light had to be lit at "
                    "sunset and put out at sunrise, every day of the year. The "
                    "lens weighed more than two tons and floated in a bath of "
                    "mercury, so that a clockwork drive could turn it. The "
                    "weights of the clockwork ran down the centre of the tower, "
                    "and the keeper on watch wound them up every forty minutes.",
                    "Each morning the lens was polished with a chamois leather "
                    "and the brass was cleaned with rouge. The wick was trimmed "
                    "so the flame burned white and steady. A smoky flame left "
                    "soot on the prisms, and soot on the prisms meant a weaker "
                    "light for the ships.",
                    "The principal keeper wrote the night's record in the "
                    "logbook: the time of lighting, the state of the sea, the "
                    "ships that passed, and any fault in the lamp.",
                ),
                _chapter(
                    "Fog",
                    "Fog was what the keepers feared most, more than any gale. "
                    "When the far buoy could no longer be seen from the "
                    "gallery, the keeper on watch started the fog signal. At "
                    "Gannet Rock this was a compressed-air horn, driven by an "
                    "engine in the lower room, and it sounded two blasts every "
                    "minute for as long as the fog lasted.",
                    "In thick fog the keepers took turns at the engine so that "
                    "it never stopped, sometimes for three days on end. They "
                    "also kept the lamp burning through the day, because a "
                    "ship that could not hear the horn might still catch the "
                    "glow of the light.",
                    "Every hour of fog was entered in the logbook, and the "
                    "hours of fog signal were counted at the end of each "
                    "month, so that the engine oil could be ordered in time.",
                ),
                _chapter(
                    "Letters Home",
                    "Keeper Harrow wrote to his wife that the frost had come "
                    "early to the mainland that year; she wrote back that the "
                    "frost had killed her beans and that the neighbours had "
                    "lit fires in their gardens, which he thought foolish. He "
                    "said that on the rock frost hardly mattered, since the "
                    "salt spray never let it settle.",
                    "He wrote too about the long evenings, the games of "
                    "draughts, and the gulls that knocked at the lantern glass "
                    "on stormy nights, dazzled by the light.",
                ),
                _chapter(
                    "Neighbours Along the Coast",
                    "Skerry Point, the next light up the coast, was a shore "
                    "station with a keeper's cottage and a garden. Its keepers "
                    "had no engine. In fog they rang a great bronze bell by "
                    "hand, and the bell can still be seen in the village "
                    "museum, with the rope worn smooth.",
                    "The keepers of the two lights never met, but they knew "
                    "each other by their lights, and on clear nights each "
                    "logbook noted whether the other light was seen. When the "
                    "Skerry Point light failed in the winter of 1903, the "
                    "Gannet Rock keepers reported it by flag to a passing "
                    "fishing boat.",
                    "Further south, the lightship at the Sound had a crew of "
                    "seven and a hand-cranked siren. Its men envied the rock "
                    "keepers their steady floor, and the rock keepers envied "
                    "the lightship men their monthly leave.",
                ),
                _chapter(
                    "The Last Keepers",
                    "In 1962 the light was converted to electricity, and the "
                    "paraffin lamp went to a museum on the mainland. A diesel "
                    "generator in the old store room now drove both the lamp "
                    "and the lens. The work changed: the keepers became "
                    "mechanics as much as lamp trimmers, and the logbook began "
                    "to fill with readings of oil pressure and battery charge.",
                    "The last three keepers left the rock in 1988, when the "
                    "light was made automatic and watched from a station on "
                    "the shore. The principal keeper locked the door, posted "
                    "the key to the lighthouse board, and wrote one last line "
                    "in the logbook: light burning, sea moderate, all well.",
                    "The tower still stands. The lantern room is empty of "
                    "people, the bunks are gone, and the gulls nest on the "
                    "gallery where the keepers once stood to watch for the "
                    "far buoy.",
                ),
            ),
        ),
        FixtureBook(
            title="A Year at Hollow Hill Orchard",
            author="Owen Pell",
            chapters=(
                _chapter(
                    "The Orchard",
                    "Hollow Hill Orchard lies in a bowl of the downs, forty "
                    "acres of apple trees and a few rows of pears. The old "
                    "trees were planted by the Pell family in the 1890s, and "
                    "the newer rows of dwarf trees in the 1960s. At blossom "
                    "time the bowl is white from rim to rim.",
                    "The orchard grows mostly cooking apples, with some "
                    "russets and a late keeping apple called Hollow Hill "
                    "Pippin, which is found nowhere else.",
                ),
                _chapter(
                    "Frost Nights",
                    "The danger month is May, when the blossom is open. A "
                    "clear, still night after a warm day can bring a frost "
                    "that kills the flowers, and with them the whole year's "
                    "crop. Cold air drains down into the bowl of the orchard "
                    "like water into a basin.",
                    "On a frost night the growers watched the thermometer by "
                    "the packing shed. When it fell to one degree above "
                    "freezing, they lit the smudge pots, small oil burners "
                    "set between every second row, and kept them burning "
                    "until the sun was up. The smoke and warmth held the "
                    "frost off the blossom.",
                    "In the worst years they also ran water sprinklers over "
                    "the young trees. The water froze on the flowers, and as "
                    "it froze it gave off enough heat to keep the blossom "
                    "inside just above freezing.",
                ),
                _chapter(
                    "Harvest",
                    "Picking begins in September with the early apples and "
                    "runs until late October. The pickers work from wooden "
                    "ladders with canvas bags slung on their fronts, and "
                    "empty the bags into bins on the trailer.",
                    "On autumn mornings fog often lies in the bowl of the "
                    "orchard until ten o'clock, and the pickers wait for it to "
                    "lift, because wet apples bruise and rot in store. The fog "
                    "lamp on the tractor was the only light in it.",
                ),
                _chapter(
                    "The Store",
                    "The apples go into a cold store behind the packing shed, "
                    "where they keep until spring. The Pippins are wrapped one "
                    "by one in paper and laid on slatted trays.",
                    "In the store a single rotten apple can spoil a whole "
                    "tray, so the trays are checked every week through the "
                    "winter and any soft fruit is taken out.",
                ),
                _chapter(
                    "Pruning",
                    "Pruning is winter work, done from December to February "
                    "while the trees are bare. The aim is an open tree, with "
                    "light reaching the middle, so that the fruit colours and "
                    "the leaves dry quickly after rain. Old Mr Pell said a "
                    "pigeon should be able to fly through the middle of a "
                    "well-pruned tree.",
                    "The pruners work on frosty mornings too, once the frost "
                    "has lifted from the branches, because frozen wood splits "
                    "under the saw. They burn the prunings in a bonfire at "
                    "the bottom of the bowl, and the smoke drifts along the "
                    "rows all afternoon.",
                    "Canker is the disease the pruners look for most. A "
                    "cankered branch is cut back to clean wood and the cut is "
                    "painted, so that the rot does not spread into the trunk.",
                ),
                _chapter(
                    "The Pell Family",
                    "The Pells came to Hollow Hill from the coast, where the "
                    "first Owen Pell had been a fisherman. He liked to say "
                    "that he had swapped one kind of weather for another, and "
                    "that a frost on the blossom was no worse than a gale on "
                    "the nets.",
                    "His grandson kept a diary of the great frost of 1895, "
                    "when the river at the foot of the downs froze so hard "
                    "that a fair was held on the ice, with stalls and a band. "
                    "The orchard was bare then, in the middle of winter, and "
                    "the frost did it no harm at all.",
                    "Today the orchard is run by a cooperative of six "
                    "families. They still sell the Pippins at the farm gate "
                    "in a wooden box, as the Pells did, and they still argue "
                    "every spring about whether the smudge pots should be "
                    "replaced with wind machines.",
                ),
            ),
        ),
        FixtureBook(
            title="The Saltmarsh Ledger",
            author="Ruth Dene",
            chapters=(
                _chapter(
                    "The Pans",
                    "On the saltmarsh the salt makers let sea water into "
                    "shallow clay pans at high tide and left the sun and wind "
                    "to dry it. In a good summer each pan gave a crust of "
                    "salt every ten days.",
                    "When fog came in from the sea it stopped the drying, and "
                    "the salt makers covered the pans with boards so the fog "
                    "would not dilute the brine.",
                ),
                _chapter(
                    "Winter Work",
                    "In winter frost cracked the clay of the pans, and the "
                    "salt makers relined them with fresh clay before spring. "
                    "On frost nights they did nothing: the frost could not be "
                    "kept off forty pans, and the clay was mended afterwards.",
                    "They rang the chapel bell when a storm tide threatened "
                    "the sea wall, so that every family on the marsh could "
                    "move its stock to higher ground.",
                ),
                _chapter(
                    "Selling the Salt",
                    "The salt went inland by cart to the market town, and by "
                    "boat along the coast. The relief boat for the lighthouse "
                    "on Gannet Rock bought a sack every month, for the keepers "
                    "salted their own fish, and the ledger notes each sale in "
                    "a careful hand.",
                    "Apple growers from the downs bought salt in autumn too, "
                    "to pack with the cider barrels, and paid in apples when "
                    "money was short. The ledger lists twelve bushels of "
                    "apples one year against four sacks of salt.",
                    "The trade ended when cheap mined salt came by railway. "
                    "The last pans were let go to the sea in 1912, and the "
                    "marsh is a bird reserve now.",
                ),
                _chapter(
                    "Marsh Weather",
                    "The ledger keeps a weather column beside the sales. Its "
                    "writer, Ruth Dene's great-aunt, noted every fog, every "
                    "frost and every gale, because each one cost the pans a "
                    "day's work or more. In the wet autumn of 1879 she counted "
                    "nineteen days of fog in October alone.",
                    "On fog days the salt makers mended baskets and sacks in "
                    "the drying shed. On frost nights they banked the fire in "
                    "the boiling house so the brine in the copper would not "
                    "freeze, and went to bed early. In a gale they walked the "
                    "sea wall with lanterns, looking for breaches, while the "
                    "light on Gannet Rock swept past them far out to sea.",
                    "The column ends in 1912 with a single word, closed, "
                    "written larger than the rest.",
                ),
            ),
        ),
    ),
    question=(
        "What did the keepers at Gannet Rock do when fog came in, and what did "
        "the growers at Hollow Hill Orchard do on frost nights?"
    ),
)
