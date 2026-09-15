#include <algorithm>
#include <cmath>
#include <fstream>
#include <iostream>
#include <sstream>
#include <string>
#include <vector>

struct Row {
    std::string symbol;
    double price{}, rsi{}, relvol{}, ret5{}, ret20{}, score{};
};

int main(int argc, char** argv) {
    if (argc < 2) {
        std::cerr << "usage: scanner <csv>\n";
        return 1;
    }
    std::ifstream in(argv[1]);
    if (!in) return 2;
    std::string line;
    std::getline(in,line);
    std::vector<Row> rows;
    while (std::getline(in,line)) {
        std::stringstream ss(line);
        Row r; std::string s;
        std::getline(ss,r.symbol,',');
        std::getline(ss,s,','); r.price=std::stod(s);
        std::getline(ss,s,','); r.rsi=std::stod(s);
        std::getline(ss,s,','); r.relvol=std::stod(s);
        std::getline(ss,s,','); r.ret5=std::stod(s);
        std::getline(ss,s,','); r.ret20=std::stod(s);
        r.score=0;
        if(r.rsi>55) r.score+=20;
        if(r.relvol>1.2) r.score+=25;
        if(r.ret5>0) r.score+=20;
        if(r.ret20>0) r.score+=20;
        if(r.price>0) r.score+=15;
        rows.push_back(r);
    }
    std::sort(rows.begin(),rows.end(),[](const Row&a,const Row&b){return a.score>b.score;});
    std::cout<<"symbol,price,rsi,relvol,ret5,ret20,score\n";
    for(size_t i=0;i<std::min<size_t>(rows.size(),50);++i)
        std::cout<<rows[i].symbol<<","<<rows[i].price<<","<<rows[i].rsi<<","<<rows[i].relvol<<","<<rows[i].ret5<<","<<rows[i].ret20<<","<<rows[i].score<<"\n";
}
