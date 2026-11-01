# SPDX-License-Identifier: Apache-2.0
"""Unit tests for unit conversion, vocabulary translation, and temperature scaling."""

from recipe_extractor.models import Ingredient, Recipe, Step
from recipe_extractor.units.convert import (
    apply_uk_vocabulary,
    convert_fahrenheit_to_celsius,
    convert_ingredient,
    convert_recipe,
    convert_text_dimensions,
    convert_text_temperatures,
    convert_text_units,
    find_ingredient_density,
    round_culinary_volume,
    round_culinary_weight,
)


def test_round_culinary_weight() -> None:
    assert round_culinary_weight(28.35) in ("28g", "30g")
    assert round_culinary_weight(113.4) == "115g"
    assert round_culinary_weight(226.8) == "225g"
    assert round_culinary_weight(453.6) == "450g"
    assert round_culinary_weight(1000) == "1kg"
    assert round_culinary_weight(1500) == "1.5kg"


def test_round_culinary_volume() -> None:
    assert round_culinary_volume(240) in ("240ml", "240.0ml")
    assert round_culinary_volume(473) == "475ml"
    assert round_culinary_volume(1000) == "1L"
    assert round_culinary_volume(1500) == "1.5L"


def test_find_ingredient_density() -> None:
    assert find_ingredient_density("all-purpose flour") == 120
    assert find_ingredient_density("granulated sugar") == 200
    assert find_ingredient_density("unsalted butter") == 227
    assert find_ingredient_density("cocoa powder") == 100
    assert find_ingredient_density("rolled oats") == 90
    assert find_ingredient_density("dragonfruit unknown") is None


def test_apply_uk_vocabulary() -> None:
    assert apply_uk_vocabulary("all-purpose flour") == "plain flour"
    assert apply_uk_vocabulary("powdered sugar") == "icing sugar"
    assert apply_uk_vocabulary("heavy cream") == "double cream"
    assert apply_uk_vocabulary("cilantro") == "fresh coriander"
    assert apply_uk_vocabulary("zucchini") == "courgette"
    assert apply_uk_vocabulary("eggplant") == "aubergine"
    assert apply_uk_vocabulary("baking soda") == "bicarbonate of soda"
    assert apply_uk_vocabulary("cornstarch") == "cornflour"
    assert apply_uk_vocabulary("scallions") == "spring onions"
    assert apply_uk_vocabulary("skillet") == "frying pan"


def test_convert_fahrenheit_to_celsius() -> None:
    conv, fan, gas = convert_fahrenheit_to_celsius(350)
    assert conv == 180
    assert fan == 160
    assert gas == "4"

    conv, fan, gas = convert_fahrenheit_to_celsius(400)
    assert conv == 200
    assert gas == "6"


def test_convert_text_temperatures() -> None:
    assert (
        convert_text_temperatures("Preheat oven to 350°F.", "uk")
        == "Preheat oven to 180°C (Gas Mark 4)."
    )
    assert (
        convert_text_temperatures("Bake at 400 degrees F for 20 mins.", "metric")
        == "Bake at 200°C for 20 mins."
    )
    assert (
        convert_text_temperatures("Preheat oven to 350°F.", "original")
        == "Preheat oven to 350°F."
    )


def test_convert_text_dimensions() -> None:
    assert (
        convert_text_dimensions("Grease a 9-inch cake pan.", "uk")
        == "Grease a 23cm cake pan."
    )
    assert (
        convert_text_dimensions("Pour into a 8x8-inch baking dish.", "metric")
        == "Pour into a 20x20cm baking dish."
    )


def test_convert_text_units_combined() -> None:
    text = "Preheat oven to 350°F. In a skillet, heat oil and add zucchini."
    converted = convert_text_units(text, "uk")
    assert "180°C (Gas Mark 4)" in converted
    assert "frying pan" in converted
    assert "courgette" in converted


def test_convert_ingredient_volume_to_weight_flour() -> None:
    ing = Ingredient(raw="2 cups all-purpose flour")
    converted_uk = convert_ingredient(ing, "uk")
    assert converted_uk.converted is not None
    assert "240g" in converted_uk.converted
    assert "plain flour" in converted_uk.converted

    converted_metric = convert_ingredient(ing, "metric")
    assert converted_metric.converted is not None
    assert "240g" in converted_metric.converted
    assert "all-purpose flour" in converted_metric.converted


def test_convert_ingredient_butter_sticks() -> None:
    ing = Ingredient(raw="1 stick unsalted butter, softened")
    converted = convert_ingredient(ing, "uk")
    assert converted.converted is not None
    assert "115g" in converted.converted
    assert "butter" in converted.converted
    assert "softened" in converted.converted


def test_convert_ingredient_weight_oz_to_g() -> None:
    ing = Ingredient(raw="8 oz cream cheese")
    converted = convert_ingredient(ing, "metric")
    assert converted.converted is not None
    assert "225g" in converted.converted
    assert "cream cheese" in converted.converted


def test_convert_ingredient_liquid_volume() -> None:
    ing = Ingredient(raw="1 cup whole milk")
    converted = convert_ingredient(ing, "uk")
    assert converted.converted is not None
    # Milk has density ~245g or volume 250ml
    assert "245g" in converted.converted or "250ml" in converted.converted


def test_convert_recipe_end_to_end() -> None:
    recipe = Recipe(
        title="American Zucchini Bread",
        ingredients=[
            Ingredient(raw="2 cups all-purpose flour"),
            Ingredient(raw="1 cup granulated sugar"),
            Ingredient(raw="1 stick butter, melted"),
            Ingredient(raw="2 cups grated zucchini"),
            Ingredient(raw="1 tsp baking soda"),
        ],
        steps=[
            Step(text="Preheat oven to 350°F."),
            Step(text="Grease a 9x5-inch loaf pan."),
            Step(text="In a skillet or bowl, mix ingredients."),
        ],
        notes=["Delicious with chocolate chips."],
    )

    uk_recipe = convert_recipe(recipe, "uk")
    assert uk_recipe.unit_system == "uk"
    assert len(uk_recipe.ingredients) == 5

    assert "240g plain flour" in (uk_recipe.ingredients[0].converted or "")
    assert "200g" in (uk_recipe.ingredients[1].converted or "")
    assert "115g butter" in (uk_recipe.ingredients[2].converted or "")
    assert "courgette" in (uk_recipe.ingredients[3].converted or "")
    assert "bicarbonate of soda" in (uk_recipe.ingredients[4].converted or "")

    assert "180°C" in uk_recipe.steps[0].text
    assert "23x13cm" in uk_recipe.steps[1].text
    assert "frying pan" in uk_recipe.steps[2].text
