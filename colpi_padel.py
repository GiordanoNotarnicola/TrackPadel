winner=0
err_nf=0
smash=0
vibora=0

for i in range(5):
    risult=input()
    if risult[0]=="w":
        winner+=1
        if risult[1]=="s":
            smash+=1
        if risult[1]=="v":
            vibora+=1
    if risult[0]=="e":
        err_nf+=1
        if risult[1]=="s":
            smash+=1
        if risult[1]=="v":
            vibora+=1

print(winner, err_nf, smash, vibora)
    
    


        
