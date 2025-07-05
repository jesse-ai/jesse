use pyo3::prelude::*;
use numpy::{PyArray1, PyReadonlyArray1};
use ndarray::{Array1, s};

/// Shift array by a given number of periods
#[pyfunction]
pub fn shift(source: PyReadonlyArray1<f64>, periods: isize) -> PyResult<Py<PyArray1<f64>>> {
    Python::with_gil(|py| {
        let source_array = source.as_array();
        let n = source_array.len();
        let mut result = Array1::<f64>::from_elem(n, f64::NAN);

        if periods == 0 {
            // No shift, return copy of source
            for i in 0..n {
                result[i] = source_array[i];
            }
        } else if periods > 0 {
            // Shift right (positive periods)
            let shift_amount = periods as usize;
            if shift_amount < n {
                for i in shift_amount..n {
                    result[i] = source_array[i - shift_amount];
                }
            }
        } else {
            // Shift left (negative periods)
            let shift_amount = (-periods) as usize;
            if shift_amount < n {
                for i in 0..(n - shift_amount) {
                    result[i] = source_array[i + shift_amount];
                }
            }
        }

        Ok(PyArray1::from_array(py, &result).to_owned())
    })
}

/// Calculate moving standard deviation
#[pyfunction]
pub fn moving_std(source: PyReadonlyArray1<f64>, period: usize) -> PyResult<Py<PyArray1<f64>>> {
    Python::with_gil(|py| {
        let source_array = source.as_array();
        let n = source_array.len();
        let mut result = Array1::<f64>::from_elem(n, f64::NAN);

        if n < period {
            return Ok(PyArray1::from_array(py, &result).to_owned());
        }

        // Calculate moving standard deviation
        for i in (period - 1)..n {
            let start_idx = i + 1 - period;
            let window = source_array.slice(s![start_idx..=i]);
            
            // Calculate mean
            let mean = window.sum() / period as f64;
            
            // Calculate variance
            let variance = window.iter()
                .map(|&x| (x - mean).powi(2))
                .sum::<f64>() / period as f64;
            
            // Calculate standard deviation
            result[i] = variance.sqrt();
        }

        Ok(PyArray1::from_array(py, &result).to_owned())
    })
}

/// Calculate Simple Moving Average (SMA)
#[pyfunction]
pub fn sma(source: PyReadonlyArray1<f64>, period: usize) -> PyResult<Py<PyArray1<f64>>> {
    Python::with_gil(|py| {
        let source_array = source.as_array();
        let n = source_array.len();
        let mut result = Array1::<f64>::from_elem(n, f64::NAN);

        if n < period {
            return Ok(PyArray1::from_array(py, &result).to_owned());
        }

        // Calculate first SMA value
        let mut sum = 0.0;
        let mut count = 0;
        for i in 0..period {
            if !source_array[i].is_nan() {
                sum += source_array[i];
                count += 1;
            }
        }
        if count > 0 {
            result[period - 1] = sum / count as f64;
        }

        // Calculate subsequent SMA values using sliding window
        for i in period..n {
            if !source_array[i - period].is_nan() {
                sum -= source_array[i - period];
                count -= 1;
            }
            if !source_array[i].is_nan() {
                sum += source_array[i];
                count += 1;
            }
            if count > 0 {
                result[i] = sum / count as f64;
            }
        }

        Ok(PyArray1::from_array(py, &result).to_owned())
    })
} 