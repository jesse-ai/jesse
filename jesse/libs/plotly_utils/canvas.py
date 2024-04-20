import numpy as np
import plotly.graph_objects as go

from plotly.subplots import make_subplots

import io
import plotly.io as pio
from PIL import Image


class Canvas:

    def __init__(self, width: int = 128, height: int = 128):
        self.fig = make_subplots(rows=1, cols=1, shared_xaxes=True)
        self.fig.update_layout(showlegend=False)
        self.fig.update_layout(
            margin=dict(l=0, r=0, t=0, b=0),
            autosize=False,
            width=width,
            height=height,
        )
        self.fig.update_xaxes(showticklabels=False)
        self.fig.update_yaxes(showticklabels=False)

    def add_candles(self, candles: np.ndarray, count: int = -1) -> None:
        self.fig.add_trace(
            go.Candlestick(
                open=candles[-count:, 1],
                close=candles[-count:, 2],
                high=candles[-count:, 3],
                low=candles[-count:, 4],
            )
        )
        self.fig.update(layout_xaxis_rangeslider_visible=False)

    def add_line(self, values: np.ndarray, count: int, **kwargs) -> None:
        self.fig.add_trace(go.Scatter(y=values[-count:], **kwargs))

    def add_area(
        self,
        higher_line: np.ndarray,
        lower_line: np.ndarray,
        count: int,
        fillcolor: str,
        **kwargs,
    ) -> None:

        self.fig.add_trace(
            go.Scatter(
                y=higher_line[-count:],
                **kwargs,
            )
        )
        self.fig.add_trace(
            go.Scatter(
                y=lower_line[-count:],
                fill="tonexty",
                fillcolor=fillcolor,
                **kwargs,
            )
        )

    def to_array(self) -> np.ndarray:
        buf = io.BytesIO()
        pio.write_image(self.fig, buf)
        img = Image.open(buf)
        return np.asarray(img)

    def show(self) -> None:
        buf = io.BytesIO()
        pio.write_image(self.fig, buf)
        img = Image.open(buf)
        img.show()

    def disable_x_axis(self) -> None:
        self.fig.update_xaxes(showticklabels=False)

    def enable_x_axis(self) -> None:
        self.fig.update_xaxes(showticklabels=True)

    def disable_y_axis(self) -> None:
        self.fig.update_yaxes(showticklabels=False)

    def enable_y_axis(self) -> None:
        self.fig.update_yaxes(showticklabels=True)
