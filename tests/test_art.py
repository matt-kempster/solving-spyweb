from spyweb.art import Crop, grid_crops


def test_grid_crops_cover_a_three_by_three_sheet() -> None:
    crops = grid_crops(611, 600)

    assert len(crops) == 9
    assert crops[0] == Crop(0, 0, 204, 200)
    assert crops[2] == Crop(407, 0, 204, 200)
    assert crops[-1] == Crop(407, 400, 204, 200)
