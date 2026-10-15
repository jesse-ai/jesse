from jesse.services.progressbar import Progressbar


def test_update_clamps_a_partial_final_step():
    progressbar = Progressbar(length=1, step=2)

    progressbar.update()

    assert progressbar.index == 1
    assert progressbar.current == 100
    assert progressbar.remaining_index == 0
    assert progressbar.is_finished is True
