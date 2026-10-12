* Exploratory workflow check; agent-written, not an author replication.
* Review input construction and sample rules before use. Choose reps >= 5.
version 16
args repetitions
if "`repetitions'"=="" local repetitions=100
clear all
set more off
adopath ++ "."
which prodest
use "firm_panel.dta", clear
isid firm_id year
keep if eligible
xtset firm_id year
gen double log_tfp_lp=.
gen double log_tfp_ols=.
tempname results
postfile `results' int industry long observations firms consecutive_pairs int lp_rc double beta_l beta_k beta_m using "industry_run_status.dta", replace
levelsof industry, local(groups)
foreach g of local groups {
    preserve
    keep if industry==`g'
    xtset firm_id year
    count
    local n=r(N)
    egen byte tag=tag(firm_id)
    count if tag
    local firms=r(N)
    count if !missing(L.ln_Y,L.ln_K,L.ln_M,L.ln_L)
    local pairs=r(N)
    local rc=2001
    local bl=.
    local bk=.
    local bm=.
    gen double lp=.
    gen double ols=.
    if `n'>=100 & `firms'>=20 & `pairs'>=50 {
        display "TRIAL INDUSTRY `g', OBS `n', FIRMS `firms', PAIRS `pairs'"
        capture noisily prodest ln_Y, free(ln_L) state(ln_K) proxy(ln_M) method(lp) id(firm_id) t(year) reps(`repetitions') seed(12345) maxiter(300)
        local rc=_rc
        if `rc'==0 {
            local bl : display %21.16g _b[ln_L]
            local bk : display %21.16g _b[ln_K]
            local bm : display %21.16g _b[ln_M]
            drop lp
            predict double lp, residuals
            replace lp=. if !e(sample)
            estimates save "lp_industry_`g'.ster", replace
        }
        regress ln_Y ln_L ln_K ln_M
        drop ols
        predict double ols if e(sample), residuals
    }
    post `results' (`g') (`n') (`firms') (`pairs') (`rc') (`bl') (`bk') (`bm')
    keep firm_id year lp ols
    tempfile one_group
    save `one_group'
    restore
    merge 1:1 firm_id year using `one_group'
    tab _merge
    assert inlist(_merge,1,3)
    assert _merge==3 if industry==`g'
    replace log_tfp_lp=lp if industry==`g'
    replace log_tfp_ols=ols if industry==`g'
    drop _merge lp ols
}
postclose `results'
gen double tfp_lp_level=exp(log_tfp_lp) if !missing(log_tfp_lp)
save "tfp_trial_results.dta", replace
export delimited using "tfp_trial_results.csv", replace
summarize log_tfp_lp log_tfp_ols, detail
preserve
use "industry_run_status.dta", clear
export delimited using "industry_run_status.csv", replace
tab lp_rc
restore
display "TFP_TRIAL_COMPLETE"
