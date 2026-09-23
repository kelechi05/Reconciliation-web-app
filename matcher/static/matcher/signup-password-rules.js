(() => {
    const passwordInput = document.querySelector("#id_password1");
    const rulesList = document.querySelector("#signup-password-rules");

    if (!passwordInput || !rulesList) {
        return;
    }

    const ruleItems = {
        length: rulesList.querySelector('[data-password-rule="length"]'),
        numeric: rulesList.querySelector('[data-password-rule="numeric"]'),
        common: rulesList.querySelector('[data-password-rule="common"]'),
        similar: rulesList.querySelector('[data-password-rule="similar"]'),
    };
    const userDetailSelectors = [
        "#id_email",
        "#id_full_name",
        "#id_company_name",
        "#id_phone_number",
    ];
    const commonPasswords = new Set([
        "12345678",
        "password",
        "password1",
        "qwerty123",
        "admin123",
        "letmein",
        "welcome",
        "welcome1",
        "iloveyou",
    ]);

    const normalize = (value) => value.toLowerCase().replace(/[^a-z0-9]/g, "");

    const isSimilarToUserDetails = (password) => {
        const normalizedPassword = normalize(password);

        if (normalizedPassword.length < 4) {
            return false;
        }

        return userDetailSelectors.some((selector) => {
            const input = document.querySelector(selector);
            const normalizedValue = normalize(input ? input.value : "");

            return (
                normalizedValue.length >= 4 &&
                (normalizedPassword.includes(normalizedValue) || normalizedValue.includes(normalizedPassword))
            );
        });
    };

    const updateRuleVisibility = () => {
        const password = passwordInput.value;

        if (!password) {
            rulesList.hidden = true;
            Object.values(ruleItems).forEach((item) => {
                if (item) {
                    item.hidden = true;
                }
            });
            return;
        }

        const brokenRules = {
            length: password.length < 8,
            numeric: /^\d+$/.test(password),
            common: commonPasswords.has(password.toLowerCase()),
            similar: isSimilarToUserDetails(password),
        };
        let hasBrokenRule = false;

        Object.entries(brokenRules).forEach(([rule, isBroken]) => {
            if (ruleItems[rule]) {
                ruleItems[rule].hidden = !isBroken;
            }

            hasBrokenRule = hasBrokenRule || isBroken;
        });

        rulesList.hidden = !hasBrokenRule;
    };

    passwordInput.addEventListener("input", updateRuleVisibility);
    userDetailSelectors.forEach((selector) => {
        const input = document.querySelector(selector);
        if (input) {
            input.addEventListener("input", updateRuleVisibility);
        }
    });
    updateRuleVisibility();
})();
