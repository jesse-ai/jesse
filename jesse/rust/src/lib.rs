use pyo3::prelude::*;

mod indicators;

use indicators::*;

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
    m.add_function(wrap_pyfunction!(bollinger_bands, m)?)?;
    
    // Utility functions (now in indicators.rs)
    m.add_function(wrap_pyfunction!(shift, m)?)?;
    m.add_function(wrap_pyfunction!(moving_std, m)?)?;
    m.add_function(wrap_pyfunction!(sma, m)?)?;
    m.add_function(wrap_pyfunction!(smma, m)?)?;
    m.add_function(wrap_pyfunction!(alligator, m)?)?;
    m.add_function(wrap_pyfunction!(di, m)?)?;
    m.add_function(wrap_pyfunction!(chop, m)?)?;
    m.add_function(wrap_pyfunction!(atr, m)?)?;
    m.add_function(wrap_pyfunction!(chande, m)?)?;
    
    Ok(())
}
