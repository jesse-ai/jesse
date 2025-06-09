use pyo3::prelude::*;
use numpy::{PyArray1, PyReadonlyArray1, PyReadonlyArray2};
use ndarray::{Array1, s};

/// Calculate RSI (Relative Strength Index)
#[pyfunction]
fn rsi(source: PyReadonlyArray1<f64>, period: usize) -> PyResult<Py<PyArray1<f64>>> {
    Python::with_gil(|py| {
        // Convert PyArray to rust ndarray
        let source_array = source.as_array();
        let n = source_array.len();
        
        // Create output array
        let mut result = Array1::<f64>::zeros(n);
        
        if n <= period {
            // Return array of NaNs if we don't have enough data
            for i in 0..n {
                result[i] = f64::NAN;
            }
            return Ok(PyArray1::from_array(py, &result).to_owned());
        }
        
        // Calculate price changes
        let mut gains = Array1::<f64>::zeros(n);
        let mut losses = Array1::<f64>::zeros(n);
        
        for i in 1..n {
            let change = source_array[i] - source_array[i - 1];
            if change > 0.0 {
                gains[i] = change;
            } else {
                losses[i] = change.abs();
            }
        }
        
        // First average gain and loss
        let mut avg_gain = gains.slice(s![1..period+1]).sum() / period as f64;
        let mut avg_loss = losses.slice(s![1..period+1]).sum() / period as f64;
        
        // Set first values as NaN
        for i in 0..period {
            result[i] = f64::NAN;
        }
        
        // Calculate first RSI
        if avg_loss == 0.0 {
            result[period] = 100.0;
        } else {
            let rs = avg_gain / avg_loss;
            result[period] = 100.0 - (100.0 / (1.0 + rs));
        }
        
        // Calculate RSI using Wilder's smoothing method
        for i in (period+1)..n {
            avg_gain = (avg_gain * (period as f64 - 1.0) + gains[i]) / period as f64;
            avg_loss = (avg_loss * (period as f64 - 1.0) + losses[i]) / period as f64;
            
            if avg_loss == 0.0 {
                result[i] = 100.0;
            } else {
                let rs = avg_gain / avg_loss;
                result[i] = 100.0 - (100.0 / (1.0 + rs));
            }
        }
        
        // Convert back to PyArray
        Ok(PyArray1::from_array(py, &result).to_owned())
    })
}

/// Calculate KAMA (Kaufman Adaptive Moving Average)
#[pyfunction]
fn kama(source: PyReadonlyArray1<f64>, period: usize, fast_length: usize, slow_length: usize) -> PyResult<Py<PyArray1<f64>>> {
    Python::with_gil(|py| {
        // Convert PyArray to rust ndarray
        let source_array = source.as_array();
        let n = source_array.len();
        
        // Create output array
        let mut result = Array1::<f64>::zeros(n);
        
        if n <= period {
            // Fill with source values when we don't have enough data
            for i in 0..n {
                result[i] = source_array[i];
            }
            return Ok(PyArray1::from_array(py, &result).to_owned());
        }
        
        // Calculate the efficiency ratio multiplier
        let fast_alpha = 2.0 / (fast_length as f64 + 1.0);
        let slow_alpha = 2.0 / (slow_length as f64 + 1.0);
        let alpha_diff = fast_alpha - slow_alpha;
        
        // First 'period' values are same as source
        for i in 0..period {
            result[i] = source_array[i];
        }
        
        // Start the calculation after the initial period
        for i in period..n {
            // Calculate Efficiency Ratio
            let change = (source_array[i] - source_array[i - period]).abs();
            let mut volatility = 0.0;
            
            for j in (i - period + 1)..=i {
                volatility += (source_array[j] - source_array[j - 1]).abs();
            }
            
            let er = if volatility != 0.0 { change / volatility } else { 0.0 };
            
            // Calculate smoothing constant
            let sc = (er * alpha_diff + slow_alpha).powi(2);
            
            // Calculate KAMA
            result[i] = result[i - 1] + sc * (source_array[i] - result[i - 1]);
        }
        
        // Convert back to PyArray
        Ok(PyArray1::from_array(py, &result).to_owned())
    })
}

/// Calculate Ichimoku Cloud
#[pyfunction]
fn ichimoku_cloud(
    candles: PyReadonlyArray2<f64>,
    conversion_line_period: usize,
    base_line_period: usize,
    lagging_line_period: usize,
    displacement: usize
) -> PyResult<(f64, f64, f64, f64)> {
    Python::with_gil(|_py| {
        let candles_array = candles.as_array();
        
        // Get the high and low price columns
        let high_prices = candles_array.slice(s![.., 3]);
        let low_prices = candles_array.slice(s![.., 4]);
        
        // Calculate for earlier period (displaced)
        let earlier_high = high_prices.slice(s![..-((displacement as isize) - 1)]);
        let earlier_low = low_prices.slice(s![..-((displacement as isize) - 1)]);
        
        // Helper function to get period high and low
        let get_period_hl = |highs: ndarray::ArrayView1<f64>, lows: ndarray::ArrayView1<f64>, period: usize| -> (f64, f64) {
            let n = highs.len();
            if n < period {
                return (f64::NAN, f64::NAN);
            }
            
            // Instead of negative slicing, use the last 'period' elements
            let start_idx = n.saturating_sub(period);
            let period_high = highs.slice(s![start_idx..]).fold(f64::NEG_INFINITY, |a, &b| a.max(b));
            let period_low = lows.slice(s![start_idx..]).fold(f64::INFINITY, |a, &b| a.min(b));
            
            (period_high, period_low)
        };
        
        // Earlier periods calculations
        let (small_ph, small_pl) = get_period_hl(earlier_high, earlier_low, conversion_line_period);
        let (mid_ph, mid_pl) = get_period_hl(earlier_high, earlier_low, base_line_period);
        let (long_ph, long_pl) = get_period_hl(earlier_high, earlier_low, lagging_line_period);
        
        let early_conversion_line = (small_ph + small_pl) / 2.0;
        let early_base_line = (mid_ph + mid_pl) / 2.0;
        let span_a = (early_conversion_line + early_base_line) / 2.0;
        let span_b = (long_ph + long_pl) / 2.0;
        
        // Current period calculations
        let (current_small_ph, current_small_pl) = get_period_hl(high_prices, low_prices, conversion_line_period);
        let (current_mid_ph, current_mid_pl) = get_period_hl(high_prices, low_prices, base_line_period);
        
        let current_conversion_line = (current_small_ph + current_small_pl) / 2.0;
        let current_base_line = (current_mid_ph + current_mid_pl) / 2.0;
        
        Ok((current_conversion_line, current_base_line, span_a, span_b))
    })
}

/// Calculate SMMA (Smoothed Moving Average)
#[pyfunction]
fn smma(source: PyReadonlyArray1<f64>, length: usize) -> PyResult<Py<PyArray1<f64>>> {
    Python::with_gil(|py| {
        // Convert PyArray to rust ndarray
        let source_array = source.as_array();
        let n = source_array.len();
        
        // Create output array
        let mut result = Array1::<f64>::zeros(n);
        
        if n < length {
            // Return array of NaNs if we don't have enough data
            for i in 0..n {
                result[i] = f64::NAN;
            }
            return Ok(PyArray1::from_array(py, &result).to_owned());
        }
        
        // Calculate first SMMA value (SMA)
        let alpha = 1.0 / (length as f64);
        let mut total = 0.0;
        for i in 0..length {
            total += source_array[i];
        }
        let init_val = total / (length as f64);
        
        // Set first value
        result[0] = alpha * source_array[0] + (init_val * (1.0 - alpha));
        
        // Calculate remaining SMMA values
        for i in 1..n {
            result[i] = alpha * source_array[i] + (1.0 - alpha) * result[i-1];
        }
        
        // Convert back to PyArray
        Ok(PyArray1::from_array(py, &result).to_owned())
    })
}

/// Shift values in array by specified periods
#[pyfunction]
fn shift(source: PyReadonlyArray1<f64>, periods: isize) -> PyResult<Py<PyArray1<f64>>> {
    Python::with_gil(|py| {
        // Convert PyArray to rust ndarray
        let source_array = source.as_array();
        let n = source_array.len();
        
        // Create output array
        let mut result = Array1::<f64>::from_elem(n, f64::NAN);
        
        if periods == 0 {
            // No shift needed
            for i in 0..n {
                result[i] = source_array[i];
            }
        } else if periods > 0 {
            // Shift right
            let shift_amount = periods as usize;
            if shift_amount < n {
                for i in shift_amount..n {
                    result[i] = source_array[i - shift_amount];
                }
            }
        } else {
            // Shift left
            let shift_amount = (-periods) as usize;
            if shift_amount < n {
                for i in 0..(n - shift_amount) {
                    result[i] = source_array[i + shift_amount];
                }
            }
        }
        
        // Convert back to PyArray
        Ok(PyArray1::from_array(py, &result).to_owned())
    })
}

/// Calculate Alligator indicator
#[pyfunction]
fn alligator(source: PyReadonlyArray1<f64>) -> PyResult<(Py<PyArray1<f64>>, Py<PyArray1<f64>>, Py<PyArray1<f64>>)> {
    Python::with_gil(|py| {
        // Convert PyArray to rust ndarray
        let source_array = source.as_array();
        
        // Calculate SMMA values
        let smma_13 = smma(source.to_owned(), 13)?;
        let smma_8 = smma(source.to_owned(), 8)?;
        let smma_5 = smma(source.to_owned(), 5)?;
        
        // Shift the SMMA values
        let jaw = shift(smma_13.extract(py)?, 8)?;
        let teeth = shift(smma_8.extract(py)?, 5)?;
        let lips = shift(smma_5.extract(py)?, 3)?;
        
        // Return the three lines
        Ok((jaw, teeth, lips))
    })
}

/// Calculate Stochastic RSI
#[pyfunction]
fn srsi(source: PyReadonlyArray1<f64>, period: usize, period_stoch: usize, k_period: usize, d_period: usize) -> PyResult<(Py<PyArray1<f64>>, Py<PyArray1<f64>>)> {
    Python::with_gil(|py| {
        // Convert PyArray to rust ndarray
        let n = source.as_array().len();
        
        // Create output arrays filled with NaN
        let mut result_k = Array1::<f64>::from_elem(n, f64::NAN);
        let mut result_d = Array1::<f64>::from_elem(n, f64::NAN);
        
        // Check if we have enough data
        if n < period + period_stoch + k_period + d_period {
            return Ok((PyArray1::from_array(py, &result_k).to_owned(), 
                      PyArray1::from_array(py, &result_d).to_owned()));
        }
        
        // Calculate RSI first
        let rsi_py = rsi(source, period)?;
        let rsi_array = unsafe { rsi_py.as_ref(py).as_array() };
        
        // Find the first valid RSI value (non-NaN)
        let mut first_valid_idx = 0;
        for i in 0..n {
            if !rsi_array[i].is_nan() {
                first_valid_idx = i;
                break;
            }
        }
        
        // Extract valid RSI values
        let valid_rsi_len = n - first_valid_idx;
        let mut valid_rsi = Vec::with_capacity(valid_rsi_len);
        for i in first_valid_idx..n {
            valid_rsi.push(rsi_array[i]);
        }
        
        // Calculate stochastic values only if we have enough data
        if valid_rsi.len() >= period_stoch {
            // Arrays to store intermediate stochastic values
            let mut stoch_k = vec![f64::NAN; valid_rsi_len];
            
            // Calculate raw %K values
            for i in period_stoch - 1..valid_rsi_len {
                let period_slice = &valid_rsi[(i - (period_stoch - 1))..=i];
                
                // Find min and max in the period
                let mut min_val = f64::INFINITY;
                let mut max_val = f64::NEG_INFINITY;
                
                for &val in period_slice {
                    if val < min_val {
                        min_val = val;
                    }
                    if val > max_val {
                        max_val = val;
                    }
                }
                
                // Calculate %K
                if max_val > min_val {
                    stoch_k[i] = 100.0 * (valid_rsi[i] - min_val) / (max_val - min_val);
                } else {
                    stoch_k[i] = 50.0; // Default value when all prices are the same
                }
            }
            
            // Smooth %K with SMA (k_period)
            let mut smoothed_k = vec![f64::NAN; valid_rsi_len];
            
            if valid_rsi_len >= period_stoch + k_period - 1 {
                for i in (period_stoch + k_period - 2)..valid_rsi_len {
                    let mut sum = 0.0;
                    for j in (i - (k_period - 1))..=i {
                        if !stoch_k[j].is_nan() {
                            sum += stoch_k[j];
                        }
                    }
                    smoothed_k[i] = sum / k_period as f64;
                }
            }
            
            // Calculate %D (SMA of smoothed %K)
            let mut smoothed_d = vec![f64::NAN; valid_rsi_len];
            
            if valid_rsi_len >= period_stoch + k_period + d_period - 2 {
                for i in (period_stoch + k_period + d_period - 3)..valid_rsi_len {
                    let mut sum = 0.0;
                    let mut count = 0;
                    for j in (i - (d_period - 1))..=i {
                        if !smoothed_k[j].is_nan() {
                            sum += smoothed_k[j];
                            count += 1;
                        }
                    }
                    if count > 0 {
                        smoothed_d[i] = sum / count as f64;
                    }
                }
            }
            
            // Copy the calculated values to the result arrays
            for i in 0..valid_rsi_len {
                let idx = first_valid_idx + i;
                result_k[idx] = smoothed_k[i];
                result_d[idx] = smoothed_d[i];
            }
        }
        
        Ok((PyArray1::from_array(py, &result_k).to_owned(), 
            PyArray1::from_array(py, &result_d).to_owned()))
    })
}

/// A Python module implemented in Rust.
#[pymodule]
fn indicatorsrust(_py: Python, m: &PyModule) -> PyResult<()> {
    m.add_function(wrap_pyfunction!(rsi, m)?)?;
    m.add_function(wrap_pyfunction!(kama, m)?)?;
    m.add_function(wrap_pyfunction!(ichimoku_cloud, m)?)?;
    m.add_function(wrap_pyfunction!(smma, m)?)?;
    m.add_function(wrap_pyfunction!(shift, m)?)?;
    m.add_function(wrap_pyfunction!(alligator, m)?)?;
    m.add_function(wrap_pyfunction!(srsi, m)?)?;
    Ok(())
}
