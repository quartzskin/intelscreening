"""
Run this once to populate the question bank.
Usage: py -3.12 seed_questions.py
"""
import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

from backend.database import init_db, SessionLocal, Question

QUESTIONS = [
    {
        "text": "What number comes next?\n```\n2,  4,  6,  8,  ?\n```",
        "option_a": "9", "option_b": "10", "option_c": "11", "option_d": "12",
        "correct_answer": "B", "difficulty": 1, "category": "number_sequence",
    },
    {
        "text": "What number comes next?\n```\n1,  4,  9,  16,  ?\n```",
        "option_a": "20", "option_b": "24", "option_c": "25", "option_d": "36",
        "correct_answer": "C", "difficulty": 2, "category": "number_sequence",
    },
    {
        "text": "What number comes next?\n```\n1,  1,  2,  3,  5,  8,  ?\n```",
        "option_a": "10", "option_b": "11", "option_c": "12", "option_d": "13",
        "correct_answer": "D", "difficulty": 2, "category": "number_sequence",
    },
    {
        "text": "What number comes next?\n```\n3,  9,  27,  81,  ?\n```",
        "option_a": "162", "option_b": "243", "option_c": "324", "option_d": "108",
        "correct_answer": "B", "difficulty": 2, "category": "number_sequence",
    },
    {
        "text": "What number comes next?\n```\n81,  27,  9,  3,  ?\n```",
        "option_a": "0", "option_b": "2", "option_c": "1", "option_d": "6",
        "correct_answer": "C", "difficulty": 2, "category": "number_sequence",
    },
    {
        "text": "What number comes next? (Triangular numbers)\n```\n1,  3,  6,  10,  15,  ?\n```",
        "option_a": "18", "option_b": "20", "option_c": "21", "option_d": "24",
        "correct_answer": "C", "difficulty": 3, "category": "number_sequence",
    },
    {
        "text": "What is the next prime number in the sequence?\n```\n2,  3,  5,  7,  11,  13,  ?\n```",
        "option_a": "14", "option_b": "15", "option_c": "16", "option_d": "17",
        "correct_answer": "D", "difficulty": 3, "category": "number_sequence",
    },
    {
        "text": "What number comes next? (Look at the differences)\n```\n2,  5,  10,  17,  26,  ?\n```",
        "option_a": "34", "option_b": "35", "option_c": "37", "option_d": "39",
        "correct_answer": "C", "difficulty": 3, "category": "number_sequence",
    },
    {
        "text": "What number comes next? (Factorials)\n```\n1,  2,  6,  24,  120,  ?\n```",
        "option_a": "240", "option_b": "360", "option_c": "600", "option_d": "720",
        "correct_answer": "D", "difficulty": 4, "category": "number_sequence",
    },
    {
        "text": "What number comes next?\n```\n7,  14,  28,  56,  ?\n```",
        "option_a": "84", "option_b": "96", "option_c": "100", "option_d": "112",
        "correct_answer": "D", "difficulty": 2, "category": "number_sequence",
    },
    {
        "text": "What number comes next?\n```\n1,  8,  27,  64,  ?\n```",
        "option_a": "100", "option_b": "125", "option_c": "144", "option_d": "216",
        "correct_answer": "B", "difficulty": 3, "category": "number_sequence",
    },
    {
        "text": "Which number is the odd one out?\n```\n2,  3,  5,  7,  11,  13,  14,  17\n```",
        "option_a": "3", "option_b": "11", "option_c": "14", "option_d": "17",
        "correct_answer": "C", "difficulty": 2, "category": "number_sequence",
    },
    {
        "text": "Which number is wrong in the sequence?\n```\n1,  4,  9,  16,  24,  36\n```",
        "option_a": "4", "option_b": "16", "option_c": "24", "option_d": "36",
        "correct_answer": "C", "difficulty": 3, "category": "number_sequence",
    },

    {
        "text": "Which letter comes next?\n```\nA,  C,  E,  G,  ?\n```",
        "option_a": "H", "option_b": "I", "option_c": "J", "option_d": "K",
        "correct_answer": "B", "difficulty": 1, "category": "letter_sequence",
    },
    {
        "text": "Which letter comes next?\n```\nZ,  X,  V,  T,  ?\n```",
        "option_a": "S", "option_b": "R", "option_c": "Q", "option_d": "P",
        "correct_answer": "B", "difficulty": 2, "category": "letter_sequence",
    },
    {
        "text": "Which letter comes next? (Differences: +1, +2, +3, +4, +5)\n```\nA,  B,  D,  G,  K,  ?\n```",
        "option_a": "N", "option_b": "O", "option_c": "P", "option_d": "Q",
        "correct_answer": "C", "difficulty": 3, "category": "letter_sequence",
    },
    {
        "text": "Which letter comes next?\n```\nB,  E,  H,  K,  ?\n```",
        "option_a": "L", "option_b": "M", "option_c": "N", "option_d": "O",
        "correct_answer": "C", "difficulty": 2, "category": "letter_sequence",
    },
    {
        "text": "Which pair comes next?\n```\nAZ,  BY,  CX,  DW,  ?\n```",
        "option_a": "EV", "option_b": "EU", "option_c": "FV", "option_d": "EW",
        "correct_answer": "A", "difficulty": 3, "category": "letter_sequence",
    },

    {
        "text": "What symbol comes next?\n```\n■  □  ■  □  ■  □  ?\n```",
        "option_a": "□", "option_b": "■", "option_c": "▪", "option_d": "▫",
        "correct_answer": "B", "difficulty": 1, "category": "pattern_visual",
    },
    {
        "text": "What completes the checkerboard pattern?\n```\nRow 1:  ●  ○  ●\nRow 2:  ○  ●  ○\nRow 3:  ●  ○  ?\n```",
        "option_a": "●", "option_b": "○", "option_c": "◐", "option_d": "◑",
        "correct_answer": "A", "difficulty": 2, "category": "pattern_visual",
    },
    {
        "text": "What number replaces the ?\n```\n| 3  | 5  | 7  |\n| 6  | 8  | 10 |\n| 9  | 11 | ?  |\n```",
        "option_a": "12", "option_b": "13", "option_c": "14", "option_d": "15",
        "correct_answer": "B", "difficulty": 2, "category": "pattern_visual",
    },
    {
        "text": "What number replaces the ? (Each row: n, n², n³)\n```\n| 2  | 4  | 8  |\n| 3  | 9  | 27 |\n| 4  | 16 | ?  |\n```",
        "option_a": "32", "option_b": "48", "option_c": "64", "option_d": "128",
        "correct_answer": "C", "difficulty": 3, "category": "pattern_visual",
    },
    {
        "text": "What number replaces the ? (Each row doubles)\n```\n| 4  | 8  | 16 |\n| 5  | 10 | 20 |\n| 6  | 12 | ?  |\n```",
        "option_a": "18", "option_b": "24", "option_c": "30", "option_d": "36",
        "correct_answer": "B", "difficulty": 2, "category": "pattern_visual",
    },
    {
        "text": "What comes next in the shape sequence?\n```\n▲   ▲▲   ▲▲▲   ▲▲▲▲   ?\n```",
        "option_a": "▲▲▲▲▲", "option_b": "▲▲▲▲▲▲", "option_c": "▲▲▲", "option_d": "▲",
        "correct_answer": "A", "difficulty": 1, "category": "pattern_visual",
    },
    {
        "text": "What replaces the ? (√ of left = right)\n```\n| 16 | 4 |\n| 9  | ? |\n```",
        "option_a": "2", "option_b": "3", "option_c": "4", "option_d": "6",
        "correct_answer": "B", "difficulty": 3, "category": "pattern_visual",
    },
    {
        "text": "What replaces the ? (x → x² → x⁴)\n```\n2  →  4   →  16\n3  →  9   →  81\n4  →  16  →  ?\n```",
        "option_a": "64", "option_b": "128", "option_c": "256", "option_d": "512",
        "correct_answer": "C", "difficulty": 4, "category": "pattern_visual",
    },
    {
        "text": "What replaces the ? (same rule each row)\n```\n3  →  9  →  81\n2  →  4  →  16\n5  →  25 →  ?\n```",
        "option_a": "125", "option_b": "225", "option_c": "250", "option_d": "625",
        "correct_answer": "D", "difficulty": 4, "category": "pattern_visual",
    },

    {
        "text": "Doctor is to Hospital as Teacher is to:",
        "option_a": "Classroom", "option_b": "School", "option_c": "Student", "option_d": "Lesson",
        "correct_answer": "B", "difficulty": 2, "category": "analogy",
    },
    {
        "text": "Hot is to Cold as Fast is to:",
        "option_a": "Speed", "option_b": "Quick", "option_c": "Slow", "option_d": "Race",
        "correct_answer": "C", "difficulty": 1, "category": "analogy",
    },
    {
        "text": "Book is to Author as Painting is to:",
        "option_a": "Museum", "option_b": "Canvas", "option_c": "Artist", "option_d": "Brush",
        "correct_answer": "C", "difficulty": 2, "category": "analogy",
    },
    {
        "text": "Glove is to Hand as Helmet is to:",
        "option_a": "Neck", "option_b": "Shoulder", "option_c": "Head", "option_d": "Ear",
        "correct_answer": "C", "difficulty": 1, "category": "analogy",
    },
    {
        "text": "Petal is to Flower as Chapter is to:",
        "option_a": "Page", "option_b": "Novel", "option_c": "Word", "option_d": "Sentence",
        "correct_answer": "B", "difficulty": 2, "category": "analogy",
    },
    {
        "text": "Ocean is to Pond as Mountain is to:",
        "option_a": "Valley", "option_b": "Cliff", "option_c": "Hill", "option_d": "River",
        "correct_answer": "C", "difficulty": 2, "category": "analogy",
    },
    {
        "text": "5 is to 25 as 7 is to:",
        "option_a": "14", "option_b": "35", "option_c": "49", "option_d": "77",
        "correct_answer": "C", "difficulty": 2, "category": "analogy",
    },
    {
        "text": "Which word does NOT belong?\n```\nCat,  Dog,  Rose,  Horse\n```",
        "option_a": "Cat", "option_b": "Dog", "option_c": "Rose", "option_d": "Horse",
        "correct_answer": "C", "difficulty": 1, "category": "analogy",
    },
    {
        "text": "If you rearrange the letters **CIFAIPC**, you get the name of:",
        "option_a": "A country", "option_b": "An ocean", "option_c": "A river", "option_d": "A mountain",
        "correct_answer": "B", "difficulty": 3, "category": "analogy",
    },

    {
        "text": "All roses are flowers. All flowers need water. Therefore:",
        "option_a": "All roses need water",
        "option_b": "Some roses need water",
        "option_c": "No roses need water",
        "option_d": "Roses are flowers that don't need water",
        "correct_answer": "A", "difficulty": 2, "category": "logic",
    },
    {
        "text": "If it rains, the ground gets wet. The ground IS wet. What can we conclude?",
        "option_a": "It definitely rained",
        "option_b": "It may or may not have rained",
        "option_c": "It did not rain",
        "option_d": "It will rain tomorrow",
        "correct_answer": "B", "difficulty": 4, "category": "logic",
    },
    {
        "text": "All Bloops are Razzies. All Razzies are Lazzies. Are all Bloops definitely Lazzies?",
        "option_a": "Yes", "option_b": "No", "option_c": "Only some", "option_d": "Cannot be determined",
        "correct_answer": "A", "difficulty": 3, "category": "logic",
    },
    {
        "text": "A bat and a ball together cost $1.10. The bat costs $1.00 MORE than the ball. How much does the ball cost?",
        "option_a": "$0.10", "option_b": "$0.05", "option_c": "$0.50", "option_d": "$0.15",
        "correct_answer": "B", "difficulty": 4, "category": "logic",
    },
    {
        "text": "You have one match. You enter a dark room with a candle, an oil lamp, and a wood stove. What do you light first?",
        "option_a": "The candle", "option_b": "The oil lamp", "option_c": "The wood stove", "option_d": "The match",
        "correct_answer": "D", "difficulty": 3, "category": "logic",
    },
    {
        "text": "Three people build three walls in three days. How many walls can SIX people build in SIX days?",
        "option_a": "6", "option_b": "9", "option_c": "12", "option_d": "18",
        "correct_answer": "C", "difficulty": 4, "category": "logic",
    },
    {
        "text": "In a room of 23 strangers, what is the approximate probability that two share a birthday?",
        "option_a": "Less than 5%", "option_b": "About 25%", "option_c": "About 50%", "option_d": "Over 90%",
        "correct_answer": "C", "difficulty": 5, "category": "logic",
    },
    {
        "text": "A square piece of paper is folded in half TWICE, then a hole is punched through all layers. When unfolded, how many holes are there?",
        "option_a": "1", "option_b": "2", "option_c": "4", "option_d": "8",
        "correct_answer": "C", "difficulty": 3, "category": "logic",
    },
    {
        "text": "What fraction is equivalent to 0.375?",
        "option_a": "1/4", "option_b": "3/8", "option_c": "2/5", "option_d": "5/8",
        "correct_answer": "B", "difficulty": 3, "category": "logic",
    },
    {
        "text": "Three switches outside a room control three bulbs inside. You may only enter ONCE. How do you determine which switch controls which bulb?",
        "option_a": "Turn all on, enter and check",
        "option_b": "Turn one on, one off, leave one on — then enter",
        "option_c": "Turn one on for several minutes, turn it off, turn another on — then enter (feel for heat)",
        "option_d": "Flip randomly until a pattern emerges",
        "correct_answer": "C", "difficulty": 5, "category": "logic",
    },
    {
        "text": "Sally's father has 4 daughters: Spring, Summer, and Autumn. What is the name of the 4th daughter?",
        "option_a": "Winter", "option_b": "Fall", "option_c": "Sally", "option_d": "Cannot be determined",
        "correct_answer": "C", "difficulty": 3, "category": "logic",
    },
    {
        "text": "A clock shows 3:15. What is the angle between the hour and minute hands?",
        "option_a": "0°", "option_b": "7.5°", "option_c": "15°", "option_d": "90°",
        "correct_answer": "B", "difficulty": 5, "category": "logic",
    },
    {
        "text": "You're in a race and you overtake the person in 2nd place. What place are you now in?",
        "option_a": "1st", "option_b": "2nd", "option_c": "3rd", "option_d": "Last",
        "correct_answer": "B", "difficulty": 2, "category": "logic",
    },
]


def seed():
    init_db()
    db = SessionLocal()
    added = 0
    try:
        for q in QUESTIONS:
            exists = db.query(Question).filter(Question.text == q["text"]).first()
            if not exists:
                db.add(Question(**q))
                added += 1
        db.commit()
        total = db.query(Question).count()
        print(f"Added {added} new questions. Total in database: {total}")
    finally:
        db.close()


if __name__ == "__main__":
    seed()
