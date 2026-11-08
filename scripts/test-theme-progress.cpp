// SPDX-License-Identifier: GPL-3.0-or-later
#include "gui/op15_progress_style.hpp"
#include <cassert>
#include <climits>
int main() {
    using namespace op15_theme;
    for (int w : {1,28,64,192,1008,1272}) for (int h : {1,28,64,192}) {
        for (int p : {-1,0,1,16,64,500,1008,1272,INT_MAX}) {
            auto s=RoundedProgress(w,h,p);
            if (p<=0 || h>w) { assert(s.body==0 && s.cap_width==0); continue; }
            assert(s.body>=0 && s.cap_width>0 && s.body+s.cap_width<=w);
            assert(s.cap_source>=0 && s.cap_source+s.cap_width==w);
            assert(s.cap_dest==s.body && s.cap_dest+s.cap_width<=w);
        }
        for (int p : {-1,0,1,16,64,500,1008,INT_MAX}) {
            int fill=SliderFillWidth(w,p,288,h);
            assert(fill>=0 && fill<=w);
            if (p<=0) assert(fill==0);
            else assert(fill>=std::min(p,w));
        }
    }
    assert(SliderFillWidth(936,400,288,192)==496);
    assert(SliderFillWidth(936,930,288,192)==936);
    assert(RoundedProgress(1008,64,0).cap_width==0);
}
