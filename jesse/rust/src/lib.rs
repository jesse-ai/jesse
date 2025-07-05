use pyo3::prelude::*;

mod indicators;
mod utils;
mod helpers;

use indicators::*;
use utils::*;
use helpers::*;

/// A Python module implemented in Rust.
#[pymodule]
fn rust(_py: Python, m: &PyModule) -> PyResult<()> {
    // Indicators
    m.add_function(wrap_pyfunction!(rsi, m)?)?;
    m.add_function(wrap_pyfunction!(kama, m)?)?;
    m.add_function(wrap_pyfunction!(ichimoku_cloud, m)?)?;
    m.add_function(wrap_pyfunction!(srsi, m)?)?;
    m.add_function(wrap_pyfunction!(adx, m)?)?;
    m.add_function(wrap_pyfunction!(tema, m)?)?;
    m.add_function(wrap_pyfunction!(macd, m)?)?;
    m.add_function(wrap_pyfunction!(bollinger_bands_width, m)?)?;
    
    // Utils
    m.add_function(wrap_pyfunction!(shift, m)?)?;
    m.add_function(wrap_pyfunction!(moving_std, m)?)?;
    m.add_function(wrap_pyfunction!(sma, m)?)?;
    
    // Helpers
    m.add_function(wrap_pyfunction!(smma, m)?)?;
    m.add_function(wrap_pyfunction!(alligator, m)?)?;
    
    Ok(())
}
