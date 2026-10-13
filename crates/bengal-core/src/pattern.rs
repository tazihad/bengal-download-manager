use anyhow::{bail, Result};

/// Generator for synthesizing sequential batch URLs from templates.
pub struct BatchPattern;

impl BatchPattern {
    /// Generates URLs by replacing an asterisk `*` in the template with numeric values.
    ///
    /// * `template` - e.g. "https://example.com/img*.jpg"
    /// * `from` - Start index (e.g. 1)
    /// * `to` - End index (e.g. 50)
    /// * `zero_pad_width` - Minimum width with leading zeros (e.g. 3 -> "001")
    pub fn generate_numeric(
        template: &str,
        from: u64,
        to: u64,
        zero_pad_width: usize,
    ) -> Result<Vec<String>> {
        if !template.contains('*') {
            bail!("Template must contain '*' wildcard");
        }
        if from > to {
            bail!("'from' index ({}) cannot exceed 'to' index ({})", from, to);
        }
        if (to - from) > 5000 {
            bail!("Batch pattern limited to max 5000 links per generation");
        }

        let mut urls = Vec::with_capacity((to - from + 1) as usize);
        for i in from..=to {
            let num_str = format!("{:0width$}", i, width = zero_pad_width);
            urls.push(template.replace('*', &num_str));
        }

        Ok(urls)
    }

    /// Generates URLs by replacing an asterisk `*` in the template with alphabetical values.
    ///
    /// * `template` - e.g. "https://example.com/part_*.zip"
    /// * `from` - e.g. 'a'
    /// * `to` - e.g. 'z'
    pub fn generate_letters(template: &str, from: char, to: char) -> Result<Vec<String>> {
        if !template.contains('*') {
            bail!("Template must contain '*' wildcard");
        }
        if from > to {
            bail!("'from' character ('{}') must precede 'to' character ('{}')", from, to);
        }
        if !from.is_ascii_alphabetic() || !to.is_ascii_alphabetic() {
            bail!("Wildcard characters must be ASCII letters (a-z or A-Z)");
        }

        let mut urls = Vec::new();
        for c in (from as u8)..=(to as u8) {
            let ch = c as char;
            urls.push(template.replace('*', &ch.to_string()));
        }

        Ok(urls)
    }

    /// Automatically expands bracket range expressions, e.g. `[01-10]` or `[a-e]`.
    pub fn expand_expression(input: &str) -> Result<Vec<String>> {
        if let Some(start_bracket) = input.find('[') {
            if let Some(end_bracket) = input[start_bracket..].find(']') {
                let end_bracket = start_bracket + end_bracket;
                let prefix = &input[..start_bracket];
                let range_str = &input[start_bracket + 1..end_bracket];
                let suffix = &input[end_bracket + 1..];

                if let Some(dash) = range_str.find('-') {
                    let from_str = range_str[..dash].trim();
                    let to_str = range_str[dash + 1..].trim();

                    // Check numeric range with possible zero padding
                    if let (Ok(from_num), Ok(to_num)) = (from_str.parse::<u64>(), to_str.parse::<u64>()) {
                        let width = from_str.len();
                        let template = format!("{}*{}", prefix, suffix);
                        return Self::generate_numeric(&template, from_num, to_num, width);
                    }

                    // Check letter range
                    if from_str.len() == 1 && to_str.len() == 1 {
                        let from_char = from_str.chars().next().unwrap();
                        let to_char = to_str.chars().next().unwrap();
                        let template = format!("{}*{}", prefix, suffix);
                        return Self::generate_letters(&template, from_char, to_char);
                    }
                }
            }
        }

        if input.contains('*') {
            Self::generate_numeric(input, 1, 10, 1)
        } else {
            Ok(vec![input.to_string()])
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_generate_numeric() {
        let urls = BatchPattern::generate_numeric("https://example.com/img*.jpg", 1, 3, 3).unwrap();
        assert_eq!(urls, vec![
            "https://example.com/img001.jpg",
            "https://example.com/img002.jpg",
            "https://example.com/img003.jpg"
        ]);
    }

    #[test]
    fn test_generate_letters() {
        let urls = BatchPattern::generate_letters("https://example.com/part_*.zip", 'a', 'c').unwrap();
        assert_eq!(urls, vec![
            "https://example.com/part_a.zip",
            "https://example.com/part_b.zip",
            "https://example.com/part_c.zip"
        ]);
    }

    #[test]
    fn test_expand_bracket_expression() {
        let urls = BatchPattern::expand_expression("https://site.com/chunk_[08-10].bin").unwrap();
        assert_eq!(urls, vec![
            "https://site.com/chunk_08.bin",
            "https://site.com/chunk_09.bin",
            "https://site.com/chunk_10.bin"
        ]);
    }
}
